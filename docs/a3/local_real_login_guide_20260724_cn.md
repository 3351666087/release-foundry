# Ashr 本地真实注册登录使用说明

## 这套登录现在是什么

这不是只在页面上假装登录。它会在本机启动五个互相配合的服务：

1. `PostgreSQL` 保存账号、凭据、成员关系和会话状态。
2. `Mailpit` 接收本地验证码邮件，避免把测试邮件发到真实邮箱。
3. `A1 Go API` 校验验证码、创建账号、签发 Cookie、读取当前账号和撤销会话。
4. `Caddy` 提供同源 HTTPS，并把 `/v1/*` 转发给 A1。
5. `A3 Webapp` 展示注册、登录和受登录状态保护的产品控制台。

这套环境只用于本地开发和演示，不等于生产邮箱、企业 SSO 或云端部署已经完成。

## 最简单的启动方法

1. 先打开 Docker Desktop，等待左下角显示 Docker Engine 正常运行。
2. 双击桌面的 `Ashr Real Login.lnk`。
3. 第一次启动会构建项目，通常比后续启动慢。
4. 登录页会自动打开：`https://localhost:4443/apps/webapp/out/login/`。
5. 本地验证码收件箱：`http://127.0.0.1:18025`。

也可以在仓库根目录双击 `start-ashr-real-login.cmd`。

## 第一次注册

1. 在登录页选择“邮箱注册”。
2. 输入名字和一个格式正确的本地测试邮箱；不要使用真实个人邮箱。
3. 勾选同意创建账号，然后点击“发送注册验证码”。
4. 页面会自动打开 Mailpit，也可以手动访问 `http://127.0.0.1:18025`。
5. 打开最新一封 `Ashr local verification code` 邮件，读取六位验证码。
6. 回到 Ashr 页面填写验证码，点击“验证并创建账号”。
7. 成功后会进入控制台。刷新页面仍保持登录，因为会话保存在 PostgreSQL，浏览器只持有 Secure/HttpOnly Cookie。

## 退出登录

控制台右上角显示当前账号名字。点击它会：

1. 调用 `POST /v1/identity/sessions/revoke`。
2. 在 PostgreSQL 租户作用域内把会话状态改为 `revoked`。
3. 清除访问 Cookie 和刷新 Cookie。
4. 返回登录页。
5. 旧 Cookie 再访问 `GET /v1/me` 会得到 `401`。

## 电脑重启后为什么网页会打不开

网页依赖 Docker 里的数据库、API、邮件收件箱和 HTTPS 代理。Windows 重启后，这些进程可能尚未启动，所以旧网址不会自己工作。重新打开 Docker Desktop，再双击 `Ashr Real Login.lnk` 即可恢复。

账号数据保存在 Docker volume `ashr-local-auth-postgres` 中。普通的停止和重启不会删除账号。不要执行删除该 volume 的命令，除非明确要清空所有本地测试账号。

## 安全边界

- 本地随机密钥保存在被 Git 忽略的 `.local-runtime/local-auth/` 中。
- `.env.local`、Cookie、验证码和本地密钥不得提交到 GitHub。
- A3 JavaScript 不能读取 HttpOnly Cookie 的值。
- Caddy 只挂载并提供 `apps/webapp/out` 构建结果；仓库源码、文档、`.env.local` 和 `.local-runtime` 均不能通过网页读取。
- Mailpit 是本地开发收件箱，不是生产 SMTP。
- Google/GitHub 首次登录仍关闭；当前已有 OAuth 路由主要是账号绑定能力。
- 当前控制台是客户端登录门禁。真正的云端产品还需要服务端路由保护、托管身份、生产邮件服务和企业部署回执。

## 停止服务

在仓库根目录运行：

```powershell
docker compose --env-file .local-runtime/local-auth/local-auth.env -f infra/docker/docker-compose.local-auth.yml down
```

该命令停止容器，但不会删除 PostgreSQL volume，因此账号会保留。
