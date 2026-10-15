# AUSTNET · 安徽理工大学校园网助手

Windows 上的校园网自动登录客户端。填一次学号和密码，之后开机自动认证、掉线自动重连，
平时缩在系统托盘里。

本仓库同时放着 [安卓版](android/README.md)（AUST网络），它的定位不一样：点开就连、
不常驻后台。

## 它能做什么

- 自动区分**有线**还是 **WiFi**，WiFi 场景会读出当前 SSID 和网卡
- 先确认对面是**安徽理工大学认证网关**（Dr.COM）再提交账号；不在校园网时不会拿着账号反复试
- 登录结果以网关的 `/drcom/chkstatus` 为准，不用「百度能不能打开」这种会被劫持骗到的判断
- 密码用 Windows DPAPI 加密后保存，磁盘上不出现明文
- 开机自启写在 `HKCU\...\CurrentVersion\Run`，不需要管理员权限
- 纯标准库 + tkinter，没有第三方依赖

## 环境要求

- Windows 10 / 11
- Python 3.8 及以上（自带 tkinter 即可）

## 怎么运行

双击 `启动.bat`，或者：

```powershell
pythonw austnet.pyw
```

命令行方式：

| 命令 | 作用 |
| --- | --- |
| `python -m austnet` | 打开图形界面 |
| `python -m austnet --tray` | 只留托盘图标，不开窗口 |
| `python -m austnet --once` | 检测并登录一次后退出 |
| `python -m austnet --selftest` | 只读自检，不提交账号密码 |
| `python -m austnet --daemon` | 命令行守护模式，Ctrl+C 停止 |

第一次建议先跑 `python -m austnet --selftest`，确认能识别到认证网关再填账号。

## 界面

上半部分是实时状态：接入方式、认证状态、本机地址、无线网络。
中间填学号、密码、登录出口，勾上「开机自动启动」和「断线自动重连」，点「保存并连接」。
下半部分是运行日志。

- 关闭窗口 = 缩到托盘，不是退出
- 退出：托盘图标右键 →「退出」
- 托盘图标颜色：绿色已认证，灰色未认证

## 认证协议

网关是 Dr.COM（`Server: DrcomServer1.0`），接口定义在 [austnet/portal.py](austnet/portal.py)。
真实登录通道是浏览器 DevTools 抓包确认的，**没有任何猜测**：

```
GET http://10.255.0.19/drcom/login
    ?callback=dr1003
    &DDDDD=<学号>@unicom
    &upass=<密码>
    &0MKKey=123456
    &R1=0&R3=0&R6=0&para=00&v6ip=&v=5425
```

注意这里**没有 `R2`**。入口页 `/a79.htm` 加载的 `a41.js` 里，
`portal_login()` 按 `page.loginMethod` 分流：本网关是 `loginMethod == 0`，
走的就是上面这条；非 0 才走 801 端口的 `?c=Portal&a=login`。程序把这条排在最后兜底。

登录通道按实测有效性排序，任一通过状态复核即算成功：

| 顺序（WiFi） | 通道 |
| --- | --- |
| 1 | `GET /drcom/login`（浏览器同款，实测有效） |
| 2 | `POST http://<host>:801/eportal/?c=Portal&a=login` |
| 3 | `POST /drcom/login` |
| 4 | `GET http://<host>:801/eportal/portal/login`（新版 ePortal，合肥校区用） |

有线连接时把 2、3 的顺序对调：`[1, 3, 2, 4]`。合肥校区的网关是 `172.24.34.2`，
已作为候选写进 `portal.CANDIDATES`，但本项目只在淮南校区实测过。

状态查询和注销：

```
GET /drcom/chkstatus?callback=dr1002    result 为 "1" 才算已认证
GET /drcom/logout?callback=dr1004
```

两个坑值得记下来：

1. `a79.htm` 的页面模板里同时写着 `authsuccess='Dr.COMWebLoginID_3.htm'` 和
   `authfail='Dr.COMWebLoginID_2.htm'`，所以只要响应里出现模板字段，就不能按关键字判成败。
   `portal.classify()` 会先认出这是登录页模板，再交给 `/drcom/chkstatus` 定夺。
2. `POST /a79.htm` 在这台网关上会返回 `Rad:userid error3`，它**不是**登录接口。
   早先按参考项目把这条排在第一位，结果每个通道都被它带偏。判断"哪种失败值得停止重试"
   时也只认凭据类错误（`密码错误` 之类），一个失败页标志不该挡住后面能成功的通道。

## 登录出口

账号提交的是「学号 + 出口后缀」，后缀在界面的下拉里选，也可以直接手填。

```
@unicom  联通
@aust    电信
@cmcc    移动
@jzg     教职工
@xyw     校园用户
（空）    不加后缀
```

注意：`a79.htm` 里内嵌的那段 `carrier` JSON 给的是 `@xyw / @dx / @lt`，和实际生效的后缀
并不一致（同一台机器上实测已认证会话的用户名是 `...@unicom`）。程序把页面里的候选
解析出来放在 `--selftest` 的输出里做参考，但最终提交哪个后缀由你在界面上决定。

## 数据放在哪

```
%LOCALAPPDATA%\AUSTNET\
├── config.json     学号、出口、网关地址、自启开关
├── secret.bin      密码（DPAPI 加密，只能被当前 Windows 用户解开）
└── austnet-*.ico   托盘图标（首次运行时生成）
```

## 打包

```powershell
.\build.ps1                  # 单文件 exe + 安装包
.\build.ps1 -SkipInstaller   # 只出 exe
```

构建依赖两个东西：

- `pip install pyinstaller`
- Inno Setup 6（`winget install -e --id JRSoftware.InnoSetup`）

中文安装向导的语言包已经放在 `installer/ChineseSimplified.isl`，不用另外下。

产物都在 `dist\`：

| 文件 | 说明 |
| --- | --- |
| `AUSTNET.exe` | 单文件绿色版，约 11.5 MB，双击即用 |
| `AUSTNET-Setup-0.1.0.exe` | 安装包，约 13 MB |

安装包的行为：装到 `%LOCALAPPDATA%\Programs\AUSTNET`，**不需要管理员权限**；建开始菜单项和
卸载项；「桌面快捷方式」和「开机自动启动」是可选项，后者默认勾选。卸载时安装器会关掉正在
运行的实例，并且**不会**删除 `%LOCALAPPDATA%\AUSTNET\` 里的配置和日志（重装还能接着用，
想彻底清掉手工删掉那个目录）。

两个打包细节值得记一下：

- `--windowed` 出来的 exe 没有控制台，所以 `--selftest` / `--once` 在打包版里改成弹窗显示结果，
  在源码里跑仍然是打印到终端。
- 图标不依赖运行时的 Pillow：`tools/make_icons.py` 预先画好 `assets/*.ico`，打包时用
  `--add-data` 带进去，PyInstaller 里 `--exclude-module PIL` 省掉十几 MB。

`autostart.entry_command()` 在打包后会改用 exe 自身的路径；程序每次启动发现自启项指向的
不是当前 exe，会自己改回来，所以从绿色版换到安装版不用手动清理注册表。

## 已知限制

- 只支持 Windows，代码里直接用了 DPAPI、注册表和 Shell_NotifyIcon
- 只在淮南校区（`10.255.0.19`）实测过，合肥校区没验证
- 登录通道走的是网页端同款接口，学校如果换认证系统或加验证码就需要跟着改
- 没做代码签名，打包后首次运行会被 SmartScreen 拦一下

## 测试

```powershell
python -m unittest discover -s tests -v
```

## 安卓版

同一套认证协议的另一端实现，Kotlin + 原生视图，详见 [android/README.md](android/README.md)。

| | 桌面版 | 安卓版 |
| --- | --- | --- |
| 打开即自动登录 | 是 | 是 |
| 断线自动重连 | 是 | 不做 |
| 后台常驻 | 系统托盘 | 不做 |
| 开机自启 | 是 | 不做 |
| 换底色 | 否 | 八种浅色可选 |

两端共用同一份协议认知：`GET /drcom/login` 是唯一实测通道（参数里没有 `R2`），
成功与否一律以 `/drcom/chkstatus` 复核。改认证逻辑时两边要一起改。

## 免责声明

本项目只供安徽理工大学在校师生学习交流使用。自动重连属于高频认证请求，若学校调整策略
导致账号受限，本项目不承担责任。使用前请确认学校允许第三方客户端登录。
