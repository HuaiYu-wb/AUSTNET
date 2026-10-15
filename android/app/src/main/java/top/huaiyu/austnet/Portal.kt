package top.huaiyu.austnet

import android.net.Network
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.io.InputStream
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.nio.ByteBuffer
import java.nio.charset.Charset
import java.nio.charset.CodingErrorAction

/**
 * Dr.COM 认证接口，逻辑和 Windows 版的 austnet/portal.py 一一对应。
 *
 * 只有 GET /drcom/login 这一条通道是实测有效的，参数就是浏览器里抓到的原样：
 * 注意没有 R2，多带会被网关当成另一套语义。
 */
object Portal {

    const val JS_VERSION = "3.3.2"

    /** 两个校区的认证网关 */
    val CANDIDATES: List<Pair<String, String>> = listOf(
        "http://10.255.0.19" to "淮南校区",
        "http://172.24.34.2" to "合肥校区",
    )

    private const val UA =
        "Mozilla/5.0 (Linux; Android 14; Mobile) AppleWebKit/537.36 " +
            "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36"

    // a79.htm 的模板里同时写着成功和失败标志，出现这些字段就不能按关键字判成败
    private val TEMPLATE_MARKERS = listOf("authloginpath", "authuserfield", "哆点参数")

    private val FAILURE_MARKERS = listOf(
        "Dr.COMWebLoginID_2", "密码错误", "账号不存在", "用户不存在", "用户名或密码",
        "认证失败", "登录失败", "密码不能为空", "余额不足", "欠费", "无权限",
        "达到并发", "Arrearage",
    )

    private val SUCCESS_MARKERS = listOf(
        "Dr.COMWebLoginID_3", "login_ok", "\"result\":1", "\"result\": 1",
        "认证成功", "登录成功", "已经在线", "已在线",
    )

    data class Response(val code: Int, val body: String)

    /**
     * state: online 已认证 / portal 需要登录 / offline 两个网关都到不了
     * reachable: 这次探测里有响应的校区，用来在界面上说清楚到底连上了哪个
     */
    data class Probe(
        val state: String,
        val base: String,
        val campus: String,
        val ip: String,
        val reachable: List<String> = emptyList(),
    )

    data class Outcome(val ok: Boolean, val message: String)

    // ---------------------------------------------------------------- 探测

    /**
     * 并行探测两个校区。
     *
     * 串行的话，另一个校区不通时要一直等到超时，白白多等好几秒；
     * 并行只花较慢那一个的时间，两边都有没有响应也能一起拿到。
     */
    fun probe(network: Network?, timeoutMs: Int = 4000): Probe {
        val found = arrayOfNulls<Probe>(CANDIDATES.size)
        val workers = CANDIDATES.mapIndexed { index, candidate ->
            Thread {
                val (base, campus) = candidate
                val json = status(base, network, timeoutMs) ?: return@Thread
                val result = json.optString("result", "").trim()
                val ip = json.optString("v46ip").ifBlank { json.optString("v4ip") }
                found[index] = Probe(
                    if (result == "1") "online" else "portal",
                    base,
                    campus,
                    ip,
                )
            }.apply {
                isDaemon = true
                start()
            }
        }
        workers.forEach { it.join((timeoutMs + 2500).toLong()) }

        val reachable = CANDIDATES.indices.mapNotNull { found[it]?.campus }
        val best = found.firstOrNull { it?.state == "online" }
            ?: found.firstOrNull { it != null }
            ?: return Probe(
                "offline",
                CANDIDATES.first().first,
                CANDIDATES.first().second,
                "",
                reachable,
            )
        return best.copy(reachable = reachable)
    }

    fun status(base: String, network: Network?, timeoutMs: Int = 5000): JSONObject? {
        val query = "callback=dr1002&jsVersion=$JS_VERSION&lang=zh&v=${randomV()}"
        val response = try {
            open("${base.trimEnd('/')}/drcom/chkstatus?$query", network, timeoutMs)
        } catch (error: Exception) {
            return null
        }
        return extractJson(response.body)
    }

    fun isOnline(base: String, network: Network?, timeoutMs: Int = 5000): Boolean =
        status(base, network, timeoutMs)?.optString("result", "")?.trim() == "1"

    // ---------------------------------------------------------------- 登录

    fun connect(
        base: String,
        account: String,
        password: String,
        network: Network?,
        timeoutMs: Int = 8000,
    ): Outcome {
        val root = base.trimEnd('/')
        val form = linkedMapOf(
            "callback" to "dr1003",
            "DDDDD" to account,
            "upass" to password,
            "0MKKey" to "123456",
            "R1" to "0",
            "R3" to "0",
            "R6" to "0",
            "para" to "00",
            "v6ip" to "",
            "v" to randomV().toString(),
        )
        val query = form.entries.joinToString("&") { "${encode(it.key)}=${encode(it.value)}" }
        val response = try {
            open("$root/drcom/login?$query", network, timeoutMs, mapOf("Referer" to "$root/a79.htm"))
        } catch (error: Exception) {
            return Outcome(false, "请求失败：${error.javaClass.simpleName}")
        }

        val (looksOk, message) = classify(response.body, response.code)
        if (pollOnline(root, network, timeoutMs)) return Outcome(true, "登录成功")
        return Outcome(
            false,
            if (looksOk) "认证接口已响应，但状态复核未通过" else message,
        )
    }

    private fun pollOnline(base: String, network: Network?, timeoutMs: Int): Boolean {
        repeat(3) { attempt ->
            if (isOnline(base, network, minOf(timeoutMs, 5000))) return true
            if (attempt < 2) Thread.sleep(1200)
        }
        return false
    }

    // ---------------------------------------------------------------- 判定

    private fun isLoginPage(text: String): Boolean =
        TEMPLATE_MARKERS.any { text.contains(it) }

    private fun classify(text: String, code: Int): Pair<Boolean, String> {
        if (isLoginPage(text)) return false to "服务器返回的是登录页，未确认认证结果"

        val json = extractJson(text)
        val message = json?.let { data ->
            listOf("msg", "msga", "res_msg", "message", "error_msg")
                .map { data.optString(it) }
                .filter { it.isNotBlank() }
                .joinToString(" ")
        }.orEmpty()

        FAILURE_MARKERS.firstOrNull { text.contains(it) }?.let { return false to it }
        SUCCESS_MARKERS.firstOrNull { text.contains(it, ignoreCase = true) }
            ?.let { return true to "登录成功" }

        if (json != null) {
            when (json.optInt("result", -1)) {
                1 -> return true to "登录成功"
                0 -> return false to message.ifBlank { "认证服务器返回失败" }
            }
        }
        if (code in 300..399) return true to "认证服务器接受了登录请求（HTTP $code）"
        return false to message.ifBlank { "响应无法识别：${text.take(120)}" }
    }

    /** 从 dr1003({...}) 这类 JSONP 里取出第一个完整 JSON 对象。 */
    fun extractJson(text: String): JSONObject? {
        val start = text.indexOf('{')
        if (start < 0) return null
        var depth = 0
        var inString = false
        var escaped = false
        for (index in start until text.length) {
            val char = text[index]
            if (inString) {
                when {
                    escaped -> escaped = false
                    char == '\\' -> escaped = true
                    char == '"' -> inString = false
                }
                continue
            }
            when (char) {
                '"' -> inString = true
                '{' -> depth++
                '}' -> {
                    depth--
                    if (depth == 0) {
                        return try {
                            JSONObject(text.substring(start, index + 1))
                        } catch (error: Exception) {
                            null
                        }
                    }
                }
            }
        }
        return null
    }

    // ---------------------------------------------------------------- HTTP

    private fun randomV(): Int = (System.currentTimeMillis() % 10000 + 500).toInt()

    private fun encode(value: String): String = URLEncoder.encode(value, "UTF-8")

    private fun open(
        url: String,
        network: Network?,
        timeoutMs: Int,
        headers: Map<String, String> = emptyMap(),
    ): Response {
        val raw = if (network != null) network.openConnection(URL(url)) else URL(url).openConnection()
        val connection = raw as HttpURLConnection
        return try {
            connection.instanceFollowRedirects = true
            connection.connectTimeout = timeoutMs
            connection.readTimeout = timeoutMs
            connection.useCaches = false
            connection.requestMethod = "GET"
            connection.setRequestProperty("User-Agent", UA)
            connection.setRequestProperty("Accept", "*/*")
            connection.setRequestProperty("Accept-Language", "zh-CN,zh;q=0.9")
            headers.forEach { (key, value) -> connection.setRequestProperty(key, value) }

            val code = connection.responseCode
            val stream = if (code >= 400) connection.errorStream else connection.inputStream
            val bytes = stream?.use { readAll(it) } ?: ByteArray(0)
            Response(code, decode(bytes, connection.contentType))
        } finally {
            connection.disconnect()
        }
    }

    private fun readAll(stream: InputStream): ByteArray {
        val sink = ByteArrayOutputStream()
        val chunk = ByteArray(8192)
        while (true) {
            val read = stream.read(chunk)
            if (read <= 0) break
            sink.write(chunk, 0, read)
        }
        return sink.toByteArray()
    }

    /** 网关返回 GBK，但字段里有 ASCII 也有中文，按顺序逐个编码试。 */
    private fun decode(bytes: ByteArray, contentType: String?): String {
        val declared = Regex("charset\\s*=\\s*['\"]?([\\w.-]+)", RegexOption.IGNORE_CASE)
            .find(contentType.orEmpty())
            ?.groupValues
            ?.get(1)
        val names = listOfNotNull(declared, "UTF-8", "GB18030", "GBK")
        for (name in names) {
            try {
                val decoder = Charset.forName(name).newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                return decoder.decode(ByteBuffer.wrap(bytes)).toString()
            } catch (error: Exception) {
                // 换下一种编码继续试
            }
        }
        return String(bytes, Charsets.UTF_8)
    }
}
