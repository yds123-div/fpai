# uv 清华源配置说明

## 配置完成情况

✅ 已成功配置 uv 使用清华大学 PyPI 镜像源

## 配置文件位置

### 1. 全局配置
- **路径**：`%USERPROFILE%\.config\uv\uv.toml`
- **作用范围**：所有使用 uv 的项目

### 2. 项目配置
- **路径**：`./uv.toml`（项目根目录）
- **作用范围**：仅当前项目

## 配置内容

```toml
# uv 配置文件
# 使用清华大学 PyPI 镜像源

[pip]
index-url = "https://pypi.tuna.tsinghua.edu.cn/simple"

# 其他配置
[global]
# 并发下载数
concurrent-downloads = 8
```

## 验证配置

### 方法 1：查看详细日志
```bash
uv pip install --dry-run <package-name> --verbose 2>&1 | Select-String "tsinghua"
```

### 方法 2：安装测试包
```bash
# 安装一个小包测试
uv pip install requests

# 观察输出，应该看到从清华源下载
```

## 常用 uv 命令

### 环境管理
```bash
# 创建虚拟环境
uv venv

# 激活虚拟环境（Windows）
.venv\Scripts\activate

# 查看当前 Python 版本
uv python list
```

### 包管理
```bash
# 安装包
uv pip install <package-name>

# 安装项目依赖
uv pip install -r requirements.txt

# 列出已安装的包
uv pip list

# 卸载包
uv pip uninstall <package-name>

# 更新包
uv pip install --upgrade <package-name>
```

### 项目管理
```bash
# 同步依赖（根据 pyproject.toml）
uv sync

# 添加依赖
uv add <package-name>

# 移除依赖
uv remove <package-name>

# 锁定依赖版本
uv lock
```

## 镜像源说明

### 清华源地址
- **主页**：https://mirrors.tuna.tsinghua.edu.cn/help/pypi/
- **索引地址**：https://pypi.tuna.tsinghua.edu.cn/simple

### 其他可用镜像源

如果需要切换到其他镜像源，修改 `index-url` 即可：

```toml
# 阿里云
index-url = "https://mirrors.aliyun.com/pypi/simple"

# 腾讯云
index-url = "https://mirrors.cloud.tencent.com/pypi/simple"

# 华为云
index-url = "https://mirrors.huaweicloud.com/repository/pypi/simple"

# 中科大
index-url = "https://pypi.mirrors.ustc.edu.cn/simple"
```

## 临时使用其他源

如果只想临时使用其他源，不修改配置文件：

```bash
uv pip install <package-name> --index-url https://pypi.org/simple
```

## 故障排查

### 问题 1：配置不生效
**解决方案**：
1. 检查配置文件路径是否正确
2. 检查 TOML 语法是否正确
3. 重启终端或 IDE

### 问题 2：下载速度慢
**解决方案**：
1. 检查网络连接
2. 尝试切换其他镜像源
3. 增加并发下载数：`concurrent-downloads = 16`

### 问题 3：包找不到
**解决方案**：
1. 某些包可能在镜像源中不存在或未同步
2. 临时使用官方源：`--index-url https://pypi.org/simple`
3. 添加额外的索引源：`extra-index-url = ["https://pypi.org/simple"]`

## 性能优化建议

1. **使用 uv 缓存**：uv 会自动缓存下载的包，无需额外配置
2. **并发下载**：已配置 `concurrent-downloads = 8`
3. **使用 uv.lock**：锁定依赖版本，加快后续安装速度

## 相关文档

- [uv 官方文档](https://docs.astral.sh/uv/)
- [清华大学开源软件镜像站](https://mirrors.tuna.tsinghua.edu.cn/)
- [uv 配置参考](https://docs.astral.sh/uv/configuration/)

---

**配置日期**：2026-04-10  
**配置状态**：✅ 已完成并验证
