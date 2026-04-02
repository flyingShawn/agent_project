# Node.js 和 npm 安装指南

## 为什么要安装 Node.js？

Node.js 是 JavaScript 运行环境，npm 是 Node.js 的包管理器。前端项目需要 Node.js 和 npm 来：
- 安装前端依赖包
- 运行前端开发服务器
- 构建前端项目

---

## 方法1：官网下载安装（推荐）

### 第一步：下载 Node.js

1. **访问官网**：https://nodejs.org/

2. **选择版本**：
   - **推荐选择**：LTS（长期支持版）- 更稳定
   - **当前版本**：20.x LTS 或 22.x LTS

3. **下载安装包**：
   - 点击 "20.11.0 LTS" 或类似按钮
   - 下载 Windows Installer (.msi)

### 第二步：安装 Node.js

1. **运行安装包**：
   - 双击下载的 `.msi` 文件
   - 点击 "Next" 继续

2. **接受许可协议**：
   - 勾选 "I accept the terms in the License Agreement"
   - 点击 "Next"

3. **选择安装路径**：
   - 默认路径：`C:\Program Files\nodejs\`
   - 可以修改，建议使用默认路径
   - 点击 "Next"

4. **选择功能**：
   - 保持默认选项即可
   - **重要**：确保勾选 "npm package manager"
   - 点击 "Next"

5. **安装**：
   - 点击 "Install"
   - 等待安装完成
   - 点击 "Finish"

### 第三步：验证安装

**打开新的命令行窗口**（重要！），然后运行：

```bash
# 检查 Node.js 版本
node --version

# 检查 npm 版本
npm --version
```

**成功标志**：
```
C:\Users\YourName> node --version
v20.11.0

C:\Users\YourName> npm --version
10.2.4
```

---

## 方法2：使用 winget 安装（Windows 10/11）

如果你的系统有 winget，可以使用命令行安装：

```bash
# 安装 Node.js LTS 版本
winget install OpenJS.NodeJS.LTS

# 或者安装最新版本
winget install OpenJS.NodeJS
```

安装完成后，**关闭并重新打开命令行窗口**，然后验证：

```bash
node --version
npm --version
```

---

## 方法3：使用 Chocolatey 安装

如果你已经安装了 Chocolatey 包管理器：

```bash
# 安装 Node.js
choco install nodejs

# 或者安装 LTS 版本
choco install nodejs-lts
```

---

## 安装后配置（可选）

### 配置 npm 镜像源（加速下载）

由于 npm 官方源在国外，下载速度可能较慢。可以配置国内镜像源：

```bash
# 配置淘宝镜像源
npm config set registry https://registry.npmmirror.com

# 验证配置
npm config get registry
```

**恢复官方源**（如果需要）：
```bash
npm config set registry https://registry.npmjs.org
```

---

## 常见问题

### 问题1：安装后命令不生效

**原因**：环境变量未生效

**解决方案**：
1. 关闭所有命令行窗口
2. 重新打开新的命令行窗口
3. 再次运行 `node --version`

如果还是不行，尝试重启电脑。

---

### 问题2：npm 下载速度慢

**解决方案**：配置国内镜像源

```bash
# 配置淘宝镜像源
npm config set registry https://registry.npmmirror.com
```

---

### 问题3：权限错误

**错误信息**：`EPERM: operation not permitted`

**解决方案**：
1. 以管理员身份运行命令行
2. 或者配置 npm 全局安装路径：

```bash
# 创建全局安装目录
mkdir %USERPROFILE%\npm-global

# 配置 npm 使用新目录
npm config set prefix "%USERPROFILE%\npm-global"

# 添加到环境变量 PATH
# 1. 右键"此电脑" -> "属性" -> "高级系统设置"
# 2. 点击"环境变量"
# 3. 在"用户变量"中找到"Path"，点击"编辑"
# 4. 添加：%USERPROFILE%\npm-global
```

---

### 问题4：PowerShell 执行策略限制

**错误信息**：
```
npm : 无法加载文件 C:\Program Files\nodejs\npm.ps1，因为在此系统上禁止运行脚本。
```

**原因**：PowerShell 默认执行策略是 Restricted，不允许运行脚本

**解决方案**：

**方法1：临时解决（推荐，安全）**
```powershell
# 在当前的 PowerShell 窗口中运行
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

# 然后运行 npm 命令
npm run dev
```
**说明**：只对当前 PowerShell 窗口有效，关闭窗口后恢复原状

---

**方法2：永久解决（当前用户）**
```powershell
# 永久更改当前用户的执行策略
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned

# 然后运行 npm 命令
npm run dev
```
**说明**：设置会保存，以后打开新的 PowerShell 窗口也会生效

---

**方法3：使用 CMD 而不是 PowerShell**
```cmd
# 打开 CMD（命令提示符）
# 按 Win + R，输入 cmd，回车

# 进入前端目录
cd D:\work_space\agent_project\agent_frontend

# 运行 npm 命令
npm run dev
```
**说明**：CMD 没有执行策略的限制，可以直接运行 npm 命令

---

**推荐方案**：使用方法1（临时解决），因为安全且简单

---

### 问题5：Node.js 版本太旧

**解决方案**：卸载旧版本，安装新版本

```bash
# 卸载旧版本（通过控制面板）
# 或者使用命令行
winget uninstall Node.js

# 然后重新安装新版本
winget install OpenJS.NodeJS.LTS
```

---

## 验证安装成功

运行项目根目录下的 `check_nodejs.bat` 文件，检查安装是否成功：

```bash
check_nodejs.bat
```

**成功输出示例**：
```
============================================================
  Checking Node.js and npm
============================================================

[Checking Node.js]
[OK] Node.js is installed
     Version: v20.11.0

[Checking npm]
[OK] npm is installed
     Version: 10.2.4

============================================================
```

---

## 安装完成后做什么？

安装 Node.js 和 npm 后，你可以：

1. **安装前端依赖**：
   ```bash
   cd agent_frontend
   npm install
   ```

2. **启动前端开发服务器**：
   ```bash
   npm run dev
   ```

3. **构建前端项目**：
   ```bash
   npm run build
   ```

---

## 推荐版本

- **Node.js**: 20.x LTS 或 22.x LTS
- **npm**: 10.x 或更高版本（随 Node.js 一起安装）

---

## 下载链接

- **Node.js 官网**：https://nodejs.org/
- **Node.js 中文网**：http://nodejs.cn/
- **npm 官网**：https://www.npmjs.com/

---

**安装完成后，请重新打开命令行窗口，然后运行 `check_nodejs.bat` 验证安装！**
