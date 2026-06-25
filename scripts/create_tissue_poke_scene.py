"""Create a simple Isaac Sim scene: a probe pokes deformable-looking tissue.

Run inside Isaac Sim Script Editor:

    exec(open("/home/renlab/issacsim/scripts/create_tissue_poke_scene.py").read())

This is a lightweight visual/kinematic demo. It creates an animated tissue mesh
with time-sampled deformation and an instrument following the poke trajectory.
"""

from math import cos, exp, pi, sin
from pathlib import Path

from pxr import Gf, Sdf, Usd, UsdGeom, UsdLux, UsdPhysics, UsdShade

try:
    import omni.usd as omni_usd
except Exception:
    omni_usd = None


OUTPUT_USD = "/home/renlab/issacsim/scenes/tissue_poke_demo.usda"

OUTPUT_PATH = Path(OUTPUT_USD)
OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)


def create_stage():
    if omni_usd is not None:
        try:
            context = omni_usd.get_context()
            context.new_stage()
            return context.get_stage(), context
        except Exception as exc:
            print(f"Falling back to standalone USD stage: {exc}")

    if OUTPUT_PATH.exists():
        OUTPUT_PATH.unlink()
    return Usd.Stage.CreateNew(OUTPUT_USD), None


STAGE, USD_CONTEXT = create_stage()


def clear_prim(path):
    prim = STAGE.GetPrimAtPath(path)
    if prim and prim.IsValid():
        STAGE.RemovePrim(path)


def define_material(path, color, roughness=0.55, metallic=0.0):
    material = UsdShade.Material.Define(STAGE, path)
    shader = UsdShade.Shader.Define(STAGE, path + "/PreviewSurface")
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*color))
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(roughness)
    shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(metallic)
    material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    return material


def bind_material(prim, material):
    UsdShade.MaterialBindingAPI(prim).Bind(material)


def add_cube(path, translate, scale, material):
    cube = UsdGeom.Cube.Define(STAGE, path)
    xform = UsdGeom.Xformable(cube)
    xform.AddTranslateOp().Set(Gf.Vec3d(*translate))
    xform.AddScaleOp().Set(Gf.Vec3f(*scale))
    bind_material(cube.GetPrim(), material)
    return cube


def animate_translate(prim, samples):
    xform = UsdGeom.Xformable(prim)
    op = xform.AddTranslateOp()
    for frame, value in samples:
        op.Set(Gf.Vec3d(*value), Usd.TimeCode(frame))


def build_tissue_mesh(path, material):
    size_x = 1.2
    size_y = 0.78
    half_x = size_x / 2.0
    half_y = size_y / 2.0
    nx = 36
    ny = 26
    z_top = 0.08
    z_bottom = -0.04
    poke_x = 0.0
    poke_y = 0.0

    def depression_at(frame, x, y):
        if frame < 25:
            depth = 0.0
        elif frame < 70:
            depth = 0.16 * (frame - 25) / 45.0
        elif frame < 115:
            depth = 0.16
        elif frame < 150:
            depth = 0.16 * (1.0 - (frame - 115) / 35.0)
        else:
            depth = 0.0

        r2 = (x - poke_x) ** 2 + (y - poke_y) ** 2
        core = exp(-r2 / (2.0 * 0.105**2))
        rim = exp(-((r2**0.5 - 0.18) ** 2) / (2.0 * 0.045**2))
        return -depth * core + 0.035 * depth / 0.16 * rim

    def make_points(frame):
        pts = []
        for j in range(ny + 1):
            y = -half_y + size_y * j / ny
            for i in range(nx + 1):
                x = -half_x + size_x * i / nx
                z = z_top + depression_at(frame, x, y)
                pts.append(Gf.Vec3f(x, y, z))
        for j in range(ny + 1):
            y = -half_y + size_y * j / ny
            for i in range(nx + 1):
                x = -half_x + size_x * i / nx
                pts.append(Gf.Vec3f(x, y, z_bottom))
        return pts

    top_offset = 0
    bottom_offset = (nx + 1) * (ny + 1)
    counts = []
    indices = []

    for j in range(ny):
        for i in range(nx):
            a = top_offset + j * (nx + 1) + i
            b = a + 1
            c = a + (nx + 1) + 1
            d = a + (nx + 1)
            counts.append(4)
            indices.extend([a, b, c, d])

    for j in range(ny):
        for i in range(nx):
            a = bottom_offset + j * (nx + 1) + i
            b = a + (nx + 1)
            c = a + (nx + 1) + 1
            d = a + 1
            counts.append(4)
            indices.extend([a, b, c, d])

    for i in range(nx):
        top_a = top_offset + i
        top_b = top_offset + i + 1
        bot_b = bottom_offset + i + 1
        bot_a = bottom_offset + i
        counts.append(4)
        indices.extend([top_a, top_b, bot_b, bot_a])

        top_a = top_offset + ny * (nx + 1) + i
        top_b = top_offset + ny * (nx + 1) + i + 1
        bot_b = bottom_offset + ny * (nx + 1) + i + 1
        bot_a = bottom_offset + ny * (nx + 1) + i
        counts.append(4)
        indices.extend([top_b, top_a, bot_a, bot_b])

    for j in range(ny):
        top_a = top_offset + j * (nx + 1)
        top_b = top_offset + (j + 1) * (nx + 1)
        bot_b = bottom_offset + (j + 1) * (nx + 1)
        bot_a = bottom_offset + j * (nx + 1)
        counts.append(4)
        indices.extend([top_b, top_a, bot_a, bot_b])

        top_a = top_offset + j * (nx + 1) + nx
        top_b = top_offset + (j + 1) * (nx + 1) + nx
        bot_b = bottom_offset + (j + 1) * (nx + 1) + nx
        bot_a = bottom_offset + j * (nx + 1) + nx
        counts.append(4)
        indices.extend([top_a, top_b, bot_b, bot_a])

    mesh = UsdGeom.Mesh.Define(STAGE, path)
    mesh.CreateFaceVertexCountsAttr(counts)
    mesh.CreateFaceVertexIndicesAttr(indices)
    mesh.CreateSubdivisionSchemeAttr("catmullClark")
    mesh.CreateDisplayColorAttr([Gf.Vec3f(0.82, 0.38, 0.34)])

    for frame in [1, 25, 50, 70, 95, 115, 150, 180]:
        mesh.GetPointsAttr().Set(make_points(frame), Usd.TimeCode(frame))

    bind_material(mesh.GetPrim(), material)
    return mesh


def build_contact_ring(path, material):
    radius = 0.18
    half_width = 0.003
    z = 0.084
    segments = 96
    points = []
    counts = []
    indices = []

    for i in range(segments):
        angle = 2.0 * pi * i / segments
        c = cos(angle)
        s = sin(angle)
        points.append(Gf.Vec3f((radius - half_width) * c, (radius - half_width) * s, z))
        points.append(Gf.Vec3f((radius + half_width) * c, (radius + half_width) * s, z))

    for i in range(segments):
        inner_a = 2 * i
        outer_a = inner_a + 1
        inner_b = 2 * ((i + 1) % segments)
        outer_b = inner_b + 1
        counts.append(4)
        indices.extend([inner_a, inner_b, outer_b, outer_a])

    ring = UsdGeom.Mesh.Define(STAGE, path)
    ring.CreatePointsAttr(points)
    ring.CreateFaceVertexCountsAttr(counts)
    ring.CreateFaceVertexIndicesAttr(indices)
    ring.CreateDisplayColorAttr([Gf.Vec3f(0.9, 0.08, 0.04)])
    bind_material(ring.GetPrim(), material)
    return ring


def build_scene():
    clear_prim("/World")

    UsdGeom.SetStageUpAxis(STAGE, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(STAGE, 1.0)
    STAGE.SetStartTimeCode(1)
    STAGE.SetEndTimeCode(180)
    STAGE.SetTimeCodesPerSecond(60)
    STAGE.SetFramesPerSecond(60)

    world = UsdGeom.Xform.Define(STAGE, "/World")
    UsdPhysics.Scene.Define(STAGE, "/World/PhysicsScene")

    tissue_mat = define_material("/World/Materials/Tissue", (0.82, 0.35, 0.32), 0.82)
    metal_mat = define_material("/World/Materials/BrushedSteel", (0.72, 0.74, 0.76), 0.32, 0.15)
    table_mat = define_material("/World/Materials/MatteTable", (0.13, 0.16, 0.17), 0.7)
    marker_mat = define_material("/World/Materials/ContactMarker", (0.9, 0.08, 0.04), 0.5)

    add_cube("/World/Table", (0, 0, -0.085), (0.8, 0.55, 0.02), table_mat)
    build_tissue_mesh("/World/TissuePatch", tissue_mat)

    build_contact_ring("/World/ContactTarget", marker_mat)

    instrument = UsdGeom.Xform.Define(STAGE, "/World/Instrument")
    animate_translate(
        instrument.GetPrim(),
        [
            (1, (0.0, 0.0, 0.62)),
            (25, (0.0, 0.0, 0.62)),
            (70, (0.0, 0.0, 0.26)),
            (115, (0.0, 0.0, 0.26)),
            (150, (0.0, 0.0, 0.62)),
            (180, (0.0, 0.0, 0.62)),
        ],
    )

    shaft = UsdGeom.Cylinder.Define(STAGE, "/World/Instrument/Shaft")
    shaft.CreateRadiusAttr(0.018)
    shaft.CreateHeightAttr(0.56)
    UsdGeom.Xformable(shaft).AddTranslateOp().Set(Gf.Vec3d(0, 0, 0.26))
    bind_material(shaft.GetPrim(), metal_mat)

    tip = UsdGeom.Cone.Define(STAGE, "/World/Instrument/Tip")
    tip.CreateRadiusAttr(0.028)
    tip.CreateHeightAttr(0.12)
    UsdGeom.Xformable(tip).AddTranslateOp().Set(Gf.Vec3d(0, 0, -0.08))
    bind_material(tip.GetPrim(), metal_mat)

    handle = UsdGeom.Cylinder.Define(STAGE, "/World/Instrument/Handle")
    handle.CreateRadiusAttr(0.055)
    handle.CreateHeightAttr(0.16)
    UsdGeom.Xformable(handle).AddTranslateOp().Set(Gf.Vec3d(0, 0, 0.58))
    bind_material(handle.GetPrim(), metal_mat)

    key = UsdLux.SphereLight.Define(STAGE, "/World/KeyLight")
    key.CreateIntensityAttr(4500)
    key.CreateRadiusAttr(1.3)
    UsdGeom.Xformable(key).AddTranslateOp().Set(Gf.Vec3d(-1.8, -1.6, 2.4))

    fill = UsdLux.DomeLight.Define(STAGE, "/World/DomeLight")
    fill.CreateIntensityAttr(280)

    camera = UsdGeom.Camera.Define(STAGE, "/World/Camera")
    cam_xform = UsdGeom.Xformable(camera)
    cam_xform.AddTranslateOp().Set(Gf.Vec3d(1.25, -1.25, 0.72))
    cam_xform.AddRotateXYZOp().Set(Gf.Vec3f(62, 0, 43))
    camera.CreateFocalLengthAttr(35)
    STAGE.SetDefaultPrim(world.GetPrim())
    STAGE.GetRootLayer().Export(OUTPUT_USD)

    if USD_CONTEXT is not None:
        USD_CONTEXT.get_selection().set_selected_prim_paths(["/World/Instrument"], True)
    print("Created scene: /World/TissuePatch and /World/Instrument.")
    print(f"Saved scene to: {OUTPUT_USD}")
    print("Press Play on the Isaac Sim timeline to watch the instrument poke the tissue.")


build_scene()
