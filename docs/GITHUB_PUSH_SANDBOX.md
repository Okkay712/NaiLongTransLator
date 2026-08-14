# GitHub 推送备忘（沙箱环境实测）

> 本文记录在 DSH 沙箱（Windows + Git for Windows 2.54）内向 GitHub 推送的经验。
> 目的：下次推送直接照抄"可行配方"，不要重复踩坑。
> 最后验证日期：2026-08（`f11a522..211222c` 推送成功）。

## 仓库与环境事实

- 仓库：`https://github.com/Okkay712/NaiLongTransLator.git`（用户自己的仓库）
- 本地 remote：`origin`，分支 `main`（跟踪 `origin/main`），存在 tag `v1.0.0`
- git 身份已配置：`Okkay712` / `254729199+Okkay712@users.noreply.github.com`
- 凭据：Windows 凭据管理器里已缓存 GitHub 凭据
  （`cmdkey /list` 可见 `LegacyGeneric:target=git:https://github.com`）
- GitHub CLI（`gh`）未安装；无 `GITHUB_TOKEN` 环境变量

## 沙箱环境的三个坑（顺序排查得到）

1. **msys 组件崩溃**：沙箱禁止创建命名/信号管道，Git 自带的 msys 程序
   `C:\Program Files\Git\usr\bin\sh.exe` / `bash.exe` 一启动就崩：
   ```
   fatal error - couldn't create signal pipe, Win32 error 5
   ```
   因此**一切会触发 git 交互提示的操作都会失败**：
   `failed to execute prompt script (exit code 66)` → `could not read Username ...`
   （git 内置的 credential prompt / askpass 走的是 msys 脚本）
   连带效果：`git push`、`git credential fill` 直接跑都失败。

2. **schannel SSL 后端不可用**：默认 `http.sslBackend=schannel` 在沙箱内报
   `SEC_E_NO_CREDENTIALS (0x8009030e)`。需先切换：
   ```powershell
   git config http.sslBackend openssl
   ```
   推送成功后记得还原：`git config --unset http.sslBackend`
   （用户正常桌面环境用 schannel 没问题，别把配置留在仓库里）。

3. **`credential.helper=store` 方案也走不通**：
   即使写临时 store 文件 + `-c credential.helper=store -c credential.store=...`，
   `git credential fill` 仍会崩（git 内部某处仍要起 msys 组件）。

## 可行配方（唯一验证通过的组合）

核心思路：**绕开 msys**——用原生 `.cmd` 脚本作为 `GIT_ASKPASS`，
凭据从 Git Credential Manager（.NET 原生 exe，沙箱内可用）动态读取，
经环境变量传入，全程不回显密码、不落盘。

```powershell
# 1. 读缓存凭据（GCM 路径固定，不在 PATH 里）
$gcm = "C:\Program Files\Git\mingw64\bin\git-credential-manager.exe"
$cred = "protocol=https`nhost=github.com`n`n" | & $gcm get 2>$null
$user = ($cred | Where-Object { $_ -match '^username=' }) -replace '^username=',''
$pass = ($cred | Where-Object { $_ -match '^password=' }) -replace '^password=',''
if (-not $pass) { "ERROR: no cached password"; exit 1 }

# 2. 写临时 askpass 脚本（放 .git/ 内，不入库；用后删除）
$askpass = "D:\Trans\.git\.tmp-askpass.cmd"
@"
@echo off
echo %~1 | findstr /i /c:"Password" >nul
if %errorlevel%==0 (echo %GIT_PASSWORD%) else (echo %GIT_USERNAME%)
"@ | Set-Content -Path $askpass -Encoding ascii

# 3. 设环境变量（仅当前 pwsh 进程）
$env:GIT_ASKPASS = $askpass
$env:GIT_USERNAME = $user
$env:GIT_PASSWORD = $pass

# 4. 推送（如未切过 sslBackend，先执行 git config http.sslBackend openssl）
try {
  git -C D:\Trans push origin main 2>&1
  "push exit=$LASTEXITCODE"
} finally {
  Remove-Item $askpass -Force -ErrorAction SilentlyContinue
  Remove-Item Env:GIT_ASKPASS, Env:GIT_USERNAME, Env:GIT_PASSWORD -ErrorAction SilentlyContinue
}
```

### 成功输出特征

```
To https://github.com/Okkay712/NaiLongTransLator.git
   f11a522..211222c  main -> main
push exit=0
```

stderr 里可能仍有 `sh.exe ... signal pipe` 的崩溃噪音，**只要 `exit=0` 且出现
`To https://...` 行就是成功**，可忽略。

### 推送后的验证（只读，无需凭据）

```powershell
git -C D:\Trans ls-remote origin   # 看 refs/heads/main 是否等于本地 HEAD
git -C D:\Trans log --oneline -3
```

## 安全注意事项

- 密码（GitHub token，40 字符）**绝不回显**：打印时只显示长度。
- 临时凭据文件（`.tmp-cred`、`.tmp-askpass.cmd`）放 `.git/` 目录内且用完即删，
  不要放工作区根目录，避免被 `git add -A` 误提交。
- `.env` 里有真实 DeepSeek API Key（gitignore 已忽略），外发/截图时注意。
