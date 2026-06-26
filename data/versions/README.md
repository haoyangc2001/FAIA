# FAIA Data Versions

`data/versions/` 记录每个可复现数据版本的总 manifest 和版本登记表。

每个版本目录应包含：

```text
data/versions/<data_version>/manifest.yaml
```

该 manifest 汇总以下信息：

```text
source config
seed
schema_version
generator_version
synthetic / processed / features / splits manifests
validation report
artifact counts
reproducibility commands
control file checksums
```

版本登记表：

```text
data/versions/version_registry.yaml
```

