"""Dr.COM / ePortal 认证接口封装。

淮南校区网关 10.255.0.19 上可用的通道（按优先级）：
  1. POST /a79.htm                      表单 DDDDD / upass / 0MKKey
  2. GET  /drcom/login                  同上，走查询串
  3. POST /drcom/login
  4. GET  http://<host>:801/eportal/portal/login   ePortal 新版接口

登录是否成功以 /drcom/chkstatus 的 result == 1 为准，不靠外网可达性判断，
避免未认证时被网关劫持造成的误判。
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
# 登录页 a41.js 里声明的 jsVersion，浏览器请求里带的就是这个值。
JS_VERSION = "3.3.2"
EPORTAL_PORT = 801
EPORTAL_ADDRESS = "BRAS"

HUAINAN = "http://10.255.0.19"
HEFEI = "http://172.24.34.2"
CANDIDATES: tuple[str, ...] = (HUAINAN, HEFEI)

SUCCESS_MARKERS = (
    "Dr.COMWebLoginID_3",
    "login_ok",
    '"result":1',
    '"result": 1',
    "认证成功",
    "登录成功",
    "已经在线",
    "已在线",
)

FAILURE_MARKERS = (
    "Dr.COMWebLoginID_2",
    "密码错误",
    "账号不存在",
    "用户不存在",
    "用户名或密码",
    "认证失败",
    "登录失败",
    "密码不能为空",
    "余额不足",
    "欠费",
    "无权限",
    "达到并发",
    "Arrearage",
)

PORTAL_MARKERS = ("Dr.COMWebLoginID", "哆点", "认证网关", "Dr.COM")

# 只有碰到这些才值得直接停止重试：换了通道也一样过不去。
DEFINITE_FAILURE_MARKERS = (
    "密码错误",
    "账号不存在",
    "用户不存在",
    "用户名或密码",
    "密码不能为空",
    "余额不足",
    "欠费",
    "无权限",
    "达到并发",
    "Arrearage",
)

# a79.htm 的页面模板里同时写着成功标志和失败标志（authsuccess / authfail），
# 所以只要响应里出现这些模板字段，就不能按文本判成功或失败。
TEMPLATE_MARKERS = ("authloginpath", "authuserfield", "哆点参数")


class PortalError(RuntimeError):
    """认证服务器不可用或返回无法解析的内容。"""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
_NO_REDIRECT_OPENER = urllib.request.build_opener(
    urllib.request.ProxyHandler({}), _NoRedirect()
)


def _decode(raw: bytes, content_type: str = "") -> str:
    match = re.search(r"charset\s*=\s*['\"]?([\w.-]+)", content_type or "", re.I)
    encodings = ([match.group(1)] if match else []) + ["utf-8", "gb18030", "gbk"]
    for encoding in encodings:
        try:
            return raw.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("utf-8", "replace")


def request(
    url: str,
    data: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 6.0,
    allow_redirect: bool = True,
) -> tuple[int, str, str]:
    """返回 (状态码, 最终 URL, 响应文本)。全局代理被显式绕过。"""
    request_headers = {
        "User-Agent": UA,
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    if headers:
        request_headers.update(headers)
    body = None
    if data is not None:
        body = urllib.parse.urlencode(data).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
    req = urllib.request.Request(
        url, data=body, headers=request_headers, method="POST" if data is not None else "GET"
    )
    opener = _OPENER if allow_redirect else _NO_REDIRECT_OPENER
    try:
        with opener.open(req, timeout=timeout) as response:
            raw = response.read(65536)
            content_type = (response.headers or {}).get("Content-Type", "")
            return getattr(response, "status", 200), response.geturl(), _decode(raw, content_type)
    except urllib.error.HTTPError as error:
        raw = error.read(65536)
        content_type = (error.headers or {}).get("Content-Type", "")
        return error.code, getattr(error, "url", url), _decode(raw, content_type)


def fetch(url: str, timeout: float = 6.0) -> str:
    return request(url, timeout=timeout)[2]


def extract_json(text: str) -> dict:
    """从 dr1002({...}) 这类 JSONP 里取第一个合法 JSON 对象。"""
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", text or ""):
        try:
            value, _ = decoder.raw_decode(text[match.start() :])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return {}


def _as_int(value: object) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def portal_page(base: str, timeout: float = 6.0) -> str:
    return fetch(base.rstrip("/") + "/a79.htm", timeout=timeout)


def identify(base: str, timeout: float = 6.0) -> tuple[bool, str]:
    """确认这个地址是不是 Dr.COM 认证网关的登录页。"""
    base = base.rstrip("/")
    try:
        html = portal_page(base, timeout=timeout)
    except (urllib.error.URLError, OSError, ValueError) as error:
        return False, "无法访问认证入口: %s" % error
    if "Dr.COMWebLoginID" in html:
        return True, "Dr.COM 认证网关"
    if any(marker in html for marker in PORTAL_MARKERS):
        return True, "疑似认证网关"
    return False, "页面不是认证网关登录页"


_CARRIER_RE = re.compile(r"carrier\s*=\s*'(.*?)'\s*;", re.S)


def exit_options(base: str, timeout: float = 6.0) -> list[tuple[str, str]]:
    """解析 a79.htm 里内嵌的出口选项，返回 [(suffix, name)]。

    注意：这段 JSON 是门户模板自带的默认值，不一定等于实际生效的后缀，
    所以只作为界面上的候选，最终提交什么由用户决定。
    """
    try:
        html = portal_page(base, timeout=timeout)
    except (urllib.error.URLError, OSError, ValueError):
        return []
    match = _CARRIER_RE.search(html)
    if not match:
        return []
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return []
    items = ((payload or {}).get("yys") or {}).get("data") or []
    options: list[tuple[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        suffix = str(item.get("suffix", ""))
        name = str(item.get("name", "")).strip() or suffix or "默认"
        options.append((suffix, name))
    return options


def status(base: str, timeout: float = 5.0) -> dict:
    """查询 Dr.COM 认证状态。"""
    base = base.rstrip("/")
    query = urllib.parse.urlencode(
        {
            "callback": "dr1002",
            "jsVersion": JS_VERSION,
            "v": str(int(time.time() * 1000) % 10000 + 500),
            "lang": "zh",
        }
    )
    text = fetch("%s/drcom/chkstatus?%s" % (base, query), timeout=timeout)
    data = extract_json(text)
    if not data:
        raise PortalError("状态接口返回内容无法解析: %s" % re.sub(r"\s+", " ", text[:120]))
    return data


def is_online(base: str, timeout: float = 5.0) -> bool:
    try:
        return str(status(base, timeout).get("result", "")).strip() == "1"
    except (PortalError, urllib.error.URLError, OSError, ValueError):
        return False


def probe(base: str, timeout: float = 5.0) -> str:
    """一次探测得到三种结果之一：

    online  —— 已通过认证；
    portal  —— 能到认证网关，需要登录；
    offline —— 到不了认证网关，多半不在校园网。
    """
    try:
        data = status(base, timeout=timeout)
    except (PortalError, urllib.error.URLError, OSError, ValueError):
        data = None
    if data is not None:
        return "online" if str(data.get("result", "")).strip() == "1" else "portal"
    # 状态接口异常时退一步看登录页本身，避免误判成离线而永远不登录。
    ok, _ = identify(base, timeout=timeout)
    return "portal" if ok else "offline"


def classify(text: str, http_status: int | None = None) -> tuple[bool, str]:
    """把登录响应归类成成功 / 失败。

    http_status 给的是 HTTP 状态码：ePortal 接口成功时只回 302、响应体为空，
    这时候光看文本是认不出来的。
    """
    if is_login_page(text):
        return False, "服务器返回的是登录页，未确认认证结果"
    data = extract_json(text)
    message = " ".join(
        str(data.get(key, ""))
        for key in ("msg", "msga", "res_msg", "message", "error_msg")
        if data.get(key)
    ).strip()
    for marker in FAILURE_MARKERS:
        if marker in (text or ""):
            return False, marker
    lowered = (text or "").lower()
    if any(marker.lower() in lowered for marker in SUCCESS_MARKERS):
        return True, "登录成功"
    if data:
        result = _as_int(data.get("result"))
        if result == 1:
            return True, "登录成功"
        if result == 0:
            return False, message or "认证服务器返回失败"
    if any(word in (text or "") for word in ("认证成功", "登录成功")):
        return True, "登录成功"
    if http_status in (301, 302, 303, 307, 308):
        return True, "认证服务器接受了登录请求（HTTP %d）" % http_status
    return False, message or "响应无法识别: %s" % re.sub(r"\s+", " ", (text or "")[:160])


def is_login_page(text: str) -> bool:
    """判断响应是不是 a79.htm 登录页模板本身。"""
    return any(marker in (text or "") for marker in TEMPLATE_MARKERS)


def is_definite_failure(text: str) -> bool:
    """服务器明确说了账号密码之类的问题，可以不再试后面的通道。

    只认凭据类错误。像 Dr.COMWebLoginID_2 这种失败页标志不算，否则一个通道
    的失败页会把后面本来能成功的通道一起挡掉。
    """
    return not is_login_page(text) and any(
        marker in (text or "") for marker in DEFINITE_FAILURE_MARKERS
    )


def _form(account: str, password: str) -> dict[str, str]:
    """浏览器 /drcom/login 请求的原样参数。

    注意：这里没有 R2。抓包看浏览器只发 R1 / R3 / R6，多带 R2 会被网关当成
    另一套语义处理。
    """
    return {
        "callback": "dr1003",
        "DDDDD": account,
        "upass": password,
        "0MKKey": "123456",
        "R1": "0",
        "R3": "0",
        "R6": "0",
        "para": "00",
        "v6ip": "",
        "v": str(int(time.time() * 1000) % 10000 + 500),
    }


def _portal_ip(base: str, fallback: str, timeout: float) -> str:
    """认证服务器看到的我方地址。

    本机可能是 192.168.x.x，但网关那边是另一个地址（chkstatus 的 v46ip）。
    未认证时 chkstatus 同样会返回 v46ip，正好可以用来填 wlanuserip。
    """
    try:
        data = status(base, timeout=timeout)
    except (PortalError, urllib.error.URLError, OSError, ValueError):
        return fallback
    value = str(data.get("v46ip") or data.get("v4ip") or "").strip()
    return value or fallback


def _channel_eportal_login(
    base: str, host: str, account: str, password: str, ip: str, mac: str, timeout: float
) -> tuple[int, str, str]:
    """ePortal 登录接口，对应页面 JS 里的 page.eportal + '?c=Portal&a=login'。

    入口页的 login_portal() 在 page.loginMethod != 0 时走这条；
    loginMethod == 0 时走的是 /drcom/login。
    """
    url = "http://%s:%d/eportal/?%s" % (
        host,
        EPORTAL_PORT,
        urllib.parse.urlencode({"c": "Portal", "a": "login"}),
    )
    data = {
        "login_method": "0",
        "user_account": account,
        "user_password": password,
        "wlan_user_ip": ip,
        "wlan_user_ipv6": "",
        "wlan_user_mac": mac,
        "wlan_ac_ip": "",
        "wlan_ac_name": "",
        "jsVersion": JS_VERSION,
    }
    return request(
        url,
        data=data,
        headers={"Referer": base + "/a79.htm"},
        timeout=timeout,
    )


def _channel_drcom_get(
    base: str, account: str, password: str, timeout: float
) -> tuple[int, str, str]:
    url = "%s/drcom/login?%s" % (base, urllib.parse.urlencode(_form(account, password)))
    return request(url, headers={"Referer": base + "/a79.htm"}, timeout=timeout)


def _channel_drcom_post(
    base: str, account: str, password: str, timeout: float
) -> tuple[int, str, str]:
    return request(
        base + "/drcom/login",
        data=_form(account, password),
        headers={"Referer": base + "/a79.htm"},
        timeout=timeout,
    )


def _channel_eportal_modern(
    host: str, account: str, password: str, ip: str, mac: str, timeout: float
) -> tuple[int, str, str]:
    """新版 ePortal 接口（合肥校区页面用这条，淮南校区返回 404）。"""
    query = urllib.parse.urlencode(
        {
            "callback": "dr1003",
            "login_method": "1",
            "user_account": ",0," + account,
            "user_password": password,
            "wlan_user_ip": ip,
            "wlan_user_mac": mac,
            "wlan_ac_ip": "",
            "wlan_ac_name": EPORTAL_ADDRESS,
            "wlan_user_ipv6": "",
            "wlan_vlan_id": "0",
            "jsVersion": JS_VERSION,
            "terminal_type": "1",
            "lang": "zh-cn",
            "v": str(int(time.time() * 1000) % 10000 + 500),
        }
    )
    url = "http://%s:%d/eportal/portal/login?%s" % (host, EPORTAL_PORT, query)
    return request(
        url, headers={"Referer": "http://%s:%d/" % (host, EPORTAL_PORT)}, timeout=timeout
    )


def _poll_online(base: str, timeout: float, attempts: int = 2, delay: float = 1.2) -> bool:
    """反复确认认证状态：网关处理登录请求有延迟，查一次可能还没生效。"""
    for index in range(attempts):
        if is_online(base, timeout=min(timeout, 5.0)):
            return True
        if index + 1 < attempts:
            time.sleep(delay)
    return False


def login(
    base: str,
    account: str,
    password: str,
    kind: str = "wifi",
    ip: str = "",
    mac: str = "",
    timeout: float = 8.0,
    verify: bool = True,
) -> tuple[bool, str]:
    """依次尝试各登录通道。

    是否成功以 /drcom/chkstatus 为准：登录接口的响应文本可能只是登录页模板，
    单看关键字容易误判。

    通道顺序按实测有效性排：淮南校区真正管用的是 GET /drcom/login，
    这一点由浏览器 DevTools 里抓到的真实请求确认过，账号后缀 @unicom。
    """
    base = base.rstrip("/")
    host = urllib.parse.urlsplit(base).hostname or ""
    portal_ip = _portal_ip(base, ip, min(timeout, 5.0))

    drcom_get = (
        "GET /drcom/login",
        lambda: _channel_drcom_get(base, account, password, timeout),
    )
    drcom_post = (
        "POST /drcom/login",
        lambda: _channel_drcom_post(base, account, password, timeout),
    )
    eportal = (
        "ePortal :801",
        lambda: _channel_eportal_login(base, host, account, password, portal_ip, mac, timeout),
    )
    eportal_modern = (
        "ePortal 新版",
        lambda: _channel_eportal_modern(host, account, password, portal_ip, mac, timeout),
    )

    # 入口页 page.loginMethod == 0 时走 /drcom/login，本网关就是这种，
    # 而且抓包确认只有 GET 这一条。有线场景把 POST 提前试。
    channels = (
        [drcom_get, drcom_post, eportal, eportal_modern]
        if kind == "wired"
        else [drcom_get, eportal, drcom_post, eportal_modern]
    )

    attempts: list[str] = []
    for label, channel in channels:
        try:
            code, _final_url, text = channel()
        except (urllib.error.URLError, OSError, ValueError) as error:
            attempts.append("%s → 请求失败：%s" % (label, error))
            continue

        ok, message = classify(text, code)
        if verify:
            if _poll_online(base, timeout):
                return True, "登录成功（%s）" % label
            attempts.append(
                "%s → %s" % (label, "接口返回正常，但状态复核未通过" if ok else message)
            )
        elif ok:
            return True, "%s（%s）" % (message, label)
        else:
            attempts.append("%s → %s" % (label, message))

        if is_definite_failure(text):
            break

    if verify and _poll_online(base, timeout, attempts=1):
        return True, "登录成功"
    return False, "；".join(attempts) or "所有登录通道均未成功"


def logout(base: str, timeout: float = 5.0) -> bool:
    base = base.rstrip("/")
    try:
        request(
            "%s/drcom/logout?%s" % (base, urllib.parse.urlencode({"callback": "dr1004"})),
            headers={"Referer": base + "/a79.htm"},
            timeout=timeout,
        )
    except (urllib.error.URLError, OSError, ValueError):
        return False
    return True
