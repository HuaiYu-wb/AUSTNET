# AUSTNET 安卓版 · AUST网络

打开即自动检测并认证的校园网客户端。不做断线重连、不做后台常驻，所以不需要前台服务，
也就绕开了安卓的后台执行限制。

## 功能

- 打开自动跑完整流程，不用手动点按钮；从后台切回来超过 8 秒也会重跑
- 同时探测淮南（`10.255.0.19`）和合肥（`172.24.34.2`）两个网关，并行发出，互不拖慢
- 已认证就直接显示结果，未认证就用保存的账号自动登录
- 密码用 Android Keystore 的 AES-GCM 加密后保存
- 八种浅色底色可选，选择会记住
- 只申请 `INTERNET` 和 `ACCESS_NETWORK_STATE` 两个权限，**不碰定位**

## 环境要求

- Android 8.0 及以上（minSdk 26，targetSdk 34）
- 构建需要 JDK 17+、Android SDK（platform-34 + build-tools 34.0.0）

## 构建

先在 `local.properties` 里填本机 SDK 路径（这个文件不进仓库）：

```
sdk.dir=F:/AndroidSDK
```

然后：

```powershell
cd android
$env:ANDROID_HOME = 'F:\AndroidSDK'
$env:ANDROID_SDK_ROOT = 'F:\AndroidSDK'
$env:GRADLE_USER_HOME = 'F:\gradle-home'   # 可选，避免撑爆 C 盘
gradle assembleRelease
```

产物在 `app/build/outputs/apk/release/app-release.apk`。

仓库里没有放 Gradle Wrapper，用系统装的 gradle 就行；想补一个的话在 `android/` 下执行
`gradle wrapper --gradle-version 8.7`。

## 签名

`app/build.gradle.kts` 会读 `android/keystore.properties`（不进仓库）：

```
storeFile=F:/AndroidKeys/AUSTNET/austnet-release.jks
storePassword=...
keyAlias=austnet
keyPassword=...
```

这个文件不存在时构建出来的就是**未签名包，装不上**。密钥库务必备份——安卓只允许同一个
签名的安装包覆盖升级，丢了以后发的版本用户只能卸载重装。

## 结构

| 文件 | 职责 |
| --- | --- |
| `Portal.kt` | Dr.COM 认证接口，逻辑对照桌面版的 `austnet/portal.py` |
| `NetInfo.kt` | 找到 WiFi 网络对象，后续请求绑定到它 |
| `Accounts.kt` | 学号和出口后缀拼接 |
| `Prefs.kt` / `SecretStore.kt` | 设置存储 + 密码加密 |
| `Palette.kt` | 底色预设 |
| `MainActivity.kt` | 界面和整个流程 |
| `tools/make_android_icons.py` | 从 `android/art/icon-source.jpg` 生成各分辨率图标 |

## 几个实现要点

**请求绑定到 WiFi 网卡。** 用 `Network.openConnection()` 而不是裸 `URL.openConnection()`。
手机同时插着卡时系统可能把请求路由到蜂窝，开着 VPN 时更会被整体劫持；绑定到具体网络
把这两个问题一起解决了。

**明文 HTTP 放行。** 认证网关只有 HTTP，而安卓 9 起默认禁止明文流量。
`res/xml/network_security_config.xml` 里只给那两个校内地址开了口子，其余仍然禁止。

**并行探测两个校区。** 串行的话，不通的那个要一直等到超时；并行只花较慢那一个的时间。

**协议和桌面版严格对齐。** 只有 `GET /drcom/login` 是实测通道，参数里**没有 `R2`**；
成功与否一律以 `/drcom/chkstatus` 复核为准——a79 的页面模板里同时写着成功和失败标志，
按关键字判会误判。

## 已知限制

- 合肥校区（`172.24.34.2`）**没有实测过**，只写了地址和探测逻辑
- 手机如果对 AUST Student 开着随机 MAC，而学校按 MAC 绑账号，会认证失败；
  需要在 WLAN 设置里改成「使用设备 MAC」
- 桌面版能做的断线自动重连、开机自启，安卓版都没有——这是刻意的取舍

