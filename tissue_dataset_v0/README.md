# Tissue Dataset V0

这是一个独立的软组织数据集生成模块，用来给后续的 NJF、response-aware representation、SOFA 联合仿真和训练代码提供统一的数据接口。

当前阶段的目标：先把“可导出的软组织交互样本”做稳定，再逐步替换 backend。仿真采集、数据结构、回放可视化和训练读取逻辑应保持解耦。

## 当前架构

模块按两个阶段组织：

- 阶段 1：Simulation + Data Logging。仿真时同步采集最终监督数据和过程日志。
- 阶段 2：Offline Replay。仿真结束后读取日志，接入 Isaac Sim、Open3D、Blender 或其他 viewer 做离线可视化。

当前默认 backend 是 `ToyPressBackend`，它不是 Isaac Sim 仿真器，而是一个 NumPy toy backend，用来验证数据结构、采集链路、日志格式和回放插件接口。另有最小 `SofaFemBackend`，可通过 `backend.type: sofa_fem` 生成 SOFA FEM slab 样本；它当前使用由 `contact_point` 和 press depth 驱动的局部 probe force，还不是完整 SOFA collision/contact 模型。Isaac Sim 当前只作为离线 replay/export viewer 使用。

## 数据样本

一个样本至少包含：

- `vertices_0`：初始网格顶点
- `vertices_1`：变形后顶点
- `displacement`：顶点位移
- `faces`：网格连接
- `action`：动作向量
- `contact_point`：接触点
- `material`：材料参数
- `meta`：样本元数据

样本目录里还会有 `logs/`：

- `logs/request.json`：本次仿真的请求快照
- `logs/summary.json`：日志摘要
- `logs/timeline.jsonl`：逐步时间线
- `logs/events.jsonl`：事件记录
- `logs/frames/frame_*.npz`：逐步状态数组
- `logs/frames/frame_*.json`：逐步标量信息

## 目录结构

```text
tissue_dataset_v0/
├── README.md
├── environment.yml
├── pyproject.toml
├── configs/
│   ├── slab_v0.yaml
│   ├── sofa_slab_v0.yaml
│   ├── sofa_liver_stage_a.yaml
│   ├── sofa_liver_stage_b.yaml
│   └── sofa_liver_stage_c.yaml
├── outputs/
├── scripts/
│   ├── generate_from_yaml.py
│   ├── generate_sample_v0.py
│   └── replay_sample.py
└── src/
    └── tissue_dataset_v0/
        ├── backend/              # backend 协议
        │   └── protocols.py
        ├── backends/             # backend 实现
        │   ├── toy_press.py
        │   └── sofa_fem.py
        ├── config/               # 默认配置和 YAML 读取
        │   ├── defaults.py
        │   └── yaml_loader.py
        ├── replay/               # replay reader / runner / viewer 插件
        │   ├── core.py
        │   └── isaacsim.py
        ├── sampling/             # action / material / scene sampler
        │   ├── action_sampler.py
        │   ├── material_sampler.py
        │   └── scene_sampler.py
        ├── layout.py
        ├── logger.py
        ├── pipeline.py
        ├── schema.py
        └── writer.py
```

## 模块职责

`schema.py` 定义样本相关的数据结构：`GeometryConfig`、`MaterialConfig`、`ActionSpec`、`LoggingConfig`、`SampleRequest` 和 `SampleResult`。

`layout.py` 定义样本字段。新增或删除训练字段时，优先改 layout，而不是把字段写死在 pipeline 里。

`backend/` 定义仿真后端协议。后续 SOFA backend、Isaac Sim backend 或真实实验 replay backend 都应实现同一接口。

`backends/` 放具体 backend 实现。当前包括 `toy_press.py` 和最小 SOFA FEM backend `sofa_fem.py`。

`sampling/` 负责从随机种子生成 material、action 和完整 scene request。

`config/yaml_loader.py` 负责把 YAML 配置转换成可执行对象，包括 backend、sampler、writer 和 generation config。YAML 的目的不是替代代码，而是把实验参数从代码中拿出来，方便批量实验、复现实验和替换模块。

`pipeline.py` 串联 backend、logger 和 writer。训练侧不需要知道仿真细节，只消费输出目录和 `sample_manifest.json`。

`replay/` 是离线回放插件框架，不重新跑仿真，只读取 `logs/`。

## YAML 使用方法

推荐从 YAML 入口生成数据：

```bash
env_isaacsim/bin/python tissue_dataset_v0/scripts/generate_from_yaml.py   tissue_dataset_v0/configs/slab_v0.yaml
```

`configs/slab_v0.yaml` 的主要字段：

- `dataset`：输出目录、样本数量、起始 sample id、随机种子
- `backend`：仿真后端类型，当前支持 `toy_press` 和 `sofa_fem`
- `geometry`：组织尺寸、网格分辨率、厚度、边界比例
- `material_sampler`：材料采样范围
- `action_sampler`：动作采样范围
- `logging`：是否记录过程日志、日志目录名、记录间隔、保存内容
- `artifacts`：最终训练样本字段的 include / exclude 裁剪

示例：

```yaml
dataset:
  output_dir: ../outputs/yaml_slab_v0
  num_samples: 3
  sample_id_start: 1
  seed: 42

backend:
  type: toy_press

logging:
  enabled: true
  log_every_n: 10

artifacts:
  include: null
  exclude: []
```

新增 backend 或 sampler 时，推荐流程是：

1. 在 `backends/` 或 `sampling/` 里新增实现类。
2. 在 `config/yaml_loader.py` 中注册新的 `type`。
3. 在 `configs/` 下新增一个 YAML 实验配置。
4. 用 `generate_from_yaml.py` 验证输出样本和日志。
5. 用 `replay_sample.py` 验证日志可回放。


### SOFA FEM backend

`configs/sofa_slab_v0.yaml` 使用 `backend.type: sofa_fem`，需要从 SOFA conda 环境运行生成命令：

```bash
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/generate_from_yaml.py \
  tissue_dataset_v0/configs/sofa_slab_v0.yaml
```

该 backend 会通过 SOFA FEM stepping 同步记录 `vertices`，并写出与 toy backend 相同的核心 sample artifacts。当前版本是最小可用物理 spike：固定 slab 底面，在 `contact_point` 附近的顶面 ROI 上施加由 press depth 和 stiffness 缩放得到的局部 downward probe force。灰色 tool sphere 仍只是离线 replay 的高处示意物，不参与 SOFA 物理，也不需要贴近表面。后续需要升级为完整 SOFA probe/collision/contact，并补充可靠的 tool pose、contact force 和 contact normal。

生成后可继续用 Isaac Sim Python 环境做离线校验和 replay/export，不会重跑 SOFA 物理：

```bash
env_isaacsim/bin/python tissue_dataset_v0/scripts/validate_sample.py \
  tissue_dataset_v0/outputs/sofa_slab_v0/sample_000001 --format json
env_isaacsim/bin/python tissue_dataset_v0/scripts/replay_sample.py \
  tissue_dataset_v0/outputs/sofa_slab_v0/sample_000001 --viewer summary --stride 1
env_isaacsim/bin/python tissue_dataset_v0/scripts/replay_sample.py \
  tissue_dataset_v0/outputs/sofa_slab_v0/sample_000001 \
  --viewer tissue_dataset_v0.replay.isaacsim:IsaacSimReplayViewer --stride 1
```


### SOFA Liver-Like Stage A

`configs/sofa_liver_stage_a.yaml` is the first Stage A config: tissue shape, topology, material, solver, and probe parameters are fixed, while action `contact_point` and `depth` are randomized. It uses `backend.extra.sofa_tissue_shape: liver_like`, a procedural organ-like deformation of the regular grid that keeps vertex count fixed for validation and future training.

Generate it from the SOFA environment:

```bash
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/generate_from_yaml.py \
  tissue_dataset_v0/configs/sofa_liver_stage_a.yaml
```

The generated samples live under `tissue_dataset_v0/outputs/sofa_liver_stage_a/`. The fixed material in this config is `youngs_modulus=5000`, `poisson_ratio=0.45`, `density=1000`, and `damping=0.5`; randomization is limited to action sampling.

Run the Stage A sanity check after generation:

```bash
env_isaacsim/bin/python tissue_dataset_v0/scripts/check_stage_a.py \
  tissue_dataset_v0/outputs/sofa_liver_stage_a
```

The checker verifies that enough samples exist, material stays fixed, action contact/depth varies, displacement magnitude is visible but bounded, and the maximum displacement remains close to the requested contact point.

The directional Stage A extension keeps the same fixed tissue/material setup but also randomizes `action[2:5]` inside a bounded upper-hemisphere cone. The first stable config uses `max_tilt_deg: 30`; a 45 degree smoke run produced one excessive-displacement sample and should be treated as later tuning work.

```bash
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/generate_from_yaml.py \
  tissue_dataset_v0/configs/sofa_liver_stage_a_directional.yaml

scripts/run_sofa_python.sh tissue_dataset_v0/scripts/check_stage_a.py \
  tissue_dataset_v0/outputs/sofa_liver_stage_a_directional_30deg \
  --min-samples 5 \
  --direction-mode varying \
  --max-tilt-deg 30 \
  --min-direction-spread-deg 5 \
  --max-contact-distance-mm 35.0
```


### SOFA Liver-Like Stage B

`configs/sofa_liver_stage_b.yaml` keeps the same fixed `liver_like` tissue shape, topology, solver settings, and localized probe approximation as Stage A, but randomizes both action and bounded material parameters. This is the first config intended to test whether material variation affects deformation while keeping geometry fixed.

Generate it from the SOFA environment:

```bash
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/generate_from_yaml.py \
  tissue_dataset_v0/configs/sofa_liver_stage_b.yaml
```

Run the varying-material sanity check after generation:

```bash
env_isaacsim/bin/python tissue_dataset_v0/scripts/check_stage_a.py \
  tissue_dataset_v0/outputs/sofa_liver_stage_b \
  --material-mode varying \
  --min-samples 5 \
  --max-max-displacement-mm 7.0 \
  --max-downward-z-mm 6.0 \
  --max-contact-distance-mm 35.0
```

Stage B sets `sofa_probe_force_material_scaling: false` so the applied probe force is not automatically scaled with Young's modulus. This lets material randomization influence deformation rather than being canceled by force scaling.


### SOFA Liver-Like Stage C

`configs/sofa_liver_stage_c.yaml` keeps the `liver_like` shape family and fixed topology, but randomizes all three independent axes: geometry size, material, and action. Geometry ranges are encoded directly in YAML with `[min, max]` values for `size_x`, `size_y`, and `thickness`; `nx`, `ny`, and `layers` remain fixed so vertex/face shapes stay batchable.

Generate it from the SOFA environment:

```bash
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/generate_from_yaml.py \
  tissue_dataset_v0/configs/sofa_liver_stage_c.yaml
```

Run the three-axis sanity check:

```bash
env_isaacsim/bin/python tissue_dataset_v0/scripts/check_stage_a.py \
  tissue_dataset_v0/outputs/sofa_liver_stage_c \
  --material-mode varying \
  --geometry-mode varying \
  --min-samples 5 \
  --max-max-displacement-mm 7.0 \
  --max-downward-z-mm 6.0 \
  --max-contact-distance-mm 35.0
```

Stage C verifies that geometry, material, and action randomization can be combined while the sampled contact point remains inside the sampled geometry and topology remains fixed.

### 生成覆盖策略

生成器默认不会覆盖或追加已有 sample 目录。如果目标目录已经存在且非空，命令会直接失败：

```text
Error: Sample directory already exists and is not empty: ... Use --overwrite to delete and regenerate it explicitly.
```

只有明确传入 `--overwrite` 时，才会删除对应 `sample_xxxxxx/` 并重新生成：

```bash
env_isaacsim/bin/python tissue_dataset_v0/scripts/generate_from_yaml.py \
  tissue_dataset_v0/configs/slab_v0.yaml \
  --overwrite
```

这个策略用于避免 `logs/timeline.jsonl` 被重复追加，或最终 artifact 与旧日志混在一起。

## 兼容命令行入口

仍然可以直接生成一个样本：

```bash
env_isaacsim/bin/python tissue_dataset_v0/scripts/generate_sample_v0.py   --output-dir tissue_dataset_v0/outputs/test_dataset   --sample-id 7
```

裁剪输出字段：

```bash
env_isaacsim/bin/python tissue_dataset_v0/scripts/generate_sample_v0.py   --output-dir tissue_dataset_v0/outputs/test_dataset_pruned   --sample-id 8   --include vertices_0   --include vertices_1   --include displacement   --include action   --include material   --include meta   --exclude faces   --exclude contact_point
```

训练侧应读取 `sample_manifest.json` 判断当前样本包含哪些字段，而不是假设所有文件都存在。

## Python 调用

```python
from pathlib import Path

from tissue_dataset_v0.config import default_sample_request
from tissue_dataset_v0.layout import default_layout
from tissue_dataset_v0.pipeline import DatasetPipeline
from tissue_dataset_v0.toy_backend import ToyPressBackend
from tissue_dataset_v0.writer import FileSystemSampleWriter

layout = default_layout()
request = default_sample_request(sample_id=1)
pipeline = DatasetPipeline(ToyPressBackend(), FileSystemSampleWriter(layout))
out_dir = pipeline.generate(Path("outputs"), request)
```


## Dataset Reader

`src/tissue_dataset_v0/dataset/` provides a manifest-driven, model-agnostic reader for generated `sample_*` directories. It reads `sample_manifest.json` first and then loads only artifacts declared as present, so future optional fields can be added or removed without changing the basic reader.

Smoke-read a generated dataset:

```bash
env_isaacsim/bin/python tissue_dataset_v0/scripts/read_dataset_smoke.py \
  tissue_dataset_v0/outputs/sofa_liver_stage_b
```

Read only selected artifacts when a future model needs a smaller input set:

```bash
env_isaacsim/bin/python tissue_dataset_v0/scripts/read_dataset_smoke.py \
  tissue_dataset_v0/outputs/sofa_liver_stage_b \
  --artifact vertices_0 \
  --artifact action \
  --artifact material \
  --artifact meta \
  --require vertices_0 \
  --require action \
  --require material \
  --require meta
```

Python usage:

```python
from tissue_dataset_v0.dataset import TissueSampleDataset

dataset = TissueSampleDataset("tissue_dataset_v0/outputs/sofa_liver_stage_b")
record = dataset[0]
vertices = record.get("vertices_0")
material = record.get("material")
summary = dataset.summary()
```

The reader reports whether array shapes are fixed across a dataset. This is important for future Stage C geometry changes: fixed topology can batch directly, while variable topology will need a model-specific collate function or graph/point-cloud batching layer.

## 回放插件

默认 summary viewer：

```bash
env_isaacsim/bin/python tissue_dataset_v0/scripts/replay_sample.py   tissue_dataset_v0/outputs/yaml_slab_v0/sample_000001   --viewer summary   --stride 10
```

Isaac Sim USD 导出 viewer：

```bash
env_isaacsim/bin/python tissue_dataset_v0/scripts/replay_sample.py   tissue_dataset_v0/outputs/yaml_slab_v0/sample_000001   --viewer tissue_dataset_v0.replay.isaacsim:IsaacSimReplayViewer   --stride 10
```

输出文件位于：

```text
sample_xxxxxx/replay_isaacsim/isaacsim_replay.usda
```

下游可视化软件只需要实现同一个 viewer 接口：

```python
class CustomReplayViewer:
    name = "custom"

    def setup(self, reader):
        ...

    def show_frame(self, frame):
        ...

    def finish(self):
        ...
```

然后通过 `module:ClassName` 加载。

## Trajectory 接口

`logs/timeline.jsonl` 和 `logs/frames/*` 现在通过 `trajectory/` 包暴露为统一的 episode trajectory 接口。这个接口不会改变现有 `sample_*` 输出，而是在日志之上提供稳定读取层：

```python
from tissue_dataset_v0.trajectory import EpisodeTrajectoryReader

reader = EpisodeTrajectoryReader("tissue_dataset_v0/outputs/trajectory_smoke/sample_990004")
for frame in reader.iter_frames(stride=30):
    vertices = frame.arrays.get("vertices")
```

每个新生成的 sample 会自动写出：

```text
logs/trajectory_summary.json
```

已有旧样本可以离线补写 summary：

```bash
env_isaacsim/bin/python tissue_dataset_v0/scripts/write_trajectory_summary.py \
  tissue_dataset_v0/outputs/overwrite_guard/sample_990003
```

replay 仍然使用原来的 `ReplayReader` 名称，但它现在是 `EpisodeTrajectoryReader` 的兼容包装。后续 Isaac Sim、SOFA 或其他平台只需要提供新的 trajectory reader，就可以复用 replay、validator 和训练读取逻辑。

## 数据校验

生成样本后，建议先运行 validator，再进入 replay 或训练：

```bash
env_isaacsim/bin/python tissue_dataset_v0/scripts/validate_sample.py \
  tissue_dataset_v0/outputs/validator_smoke/sample_990001
```

validator 位于 `src/tissue_dataset_v0/validation/`，采用规则插件结构。默认规则会检查：

- `sample_manifest.json` 与实际 artifact 文件是否一致
- `.npy` shape / dtype 是否和 manifest 一致
- `vertices_0`、`vertices_1`、`displacement` 是否形状一致，且位移值是否匹配
- `faces` 是否引用合法 vertex index
- `meta.json`、`material.json`、`logs/request.json` 的共享字段是否一致
- `logs/timeline.jsonl` 是否有重复或倒退 step
- timeline 引用的 `frames/*.npz` 和 `frames/*.json` 是否存在且 key 一致
- `logs/trajectory_summary.json` 存在时是否和日志内容一致

后续迁移到 Isaac Sim、SOFA 或新增字段时，不需要改 CLI 主流程。可以增加新的规则类，然后通过 `--rule module:ClassName` 接入：

```bash
env_isaacsim/bin/python tissue_dataset_v0/scripts/validate_sample.py \
  path/to/sample_000001 \
  --rule my_package.validation:IsaacSimSpecificRule
```

## 给 Codex 的工作提示

后续继续开发时，请优先遵守这些约束：

- 不要把仿真器、采样器、数据写出和可视化揉到一个脚本里。
- 新仿真器放入 `backends/`，并实现 `SimulationBackend` 协议。
- 新 action 或 material 采样逻辑放入 `sampling/`。
- 新实验参数优先写进 `configs/*.yaml`。
- 新训练字段优先通过 `layout.py` 和 `writer.py` 扩展。
- 新可视化工具放入 `replay/`，实现 `ReplayViewer` 接口。
- Isaac Sim 当前是 replay/export backend，不是默认 simulation backend。
- 修改后至少运行一次 YAML 生成和一次 replay 验证。
