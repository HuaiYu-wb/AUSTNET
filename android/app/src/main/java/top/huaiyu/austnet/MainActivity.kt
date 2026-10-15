package top.huaiyu.austnet

import android.graphics.Color
import android.graphics.drawable.ColorDrawable
import android.graphics.drawable.Drawable
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.view.View
import android.widget.CheckBox
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.google.android.material.button.MaterialButton
import com.google.android.material.textfield.MaterialAutoCompleteTextView
import com.google.android.material.textfield.TextInputEditText
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/** 从后台切回来别重复打扰网关，两次自动检测至少隔这么久 */
private const val RETRY_GUARD_MS = 8000L

/**
 * 单页应用：打开就检测，需要认证就自动登录。
 *
 * 不做断线重连、不做后台常驻，所以不需要前台服务，也就避开了安卓的后台执行限制。
 */
class MainActivity : AppCompatActivity() {

    private lateinit var prefs: Prefs

    private lateinit var stateText: TextView
    private lateinit var detailText: TextView
    private lateinit var logText: TextView
    private lateinit var accountInput: TextInputEditText
    private lateinit var passwordInput: TextInputEditText
    private lateinit var exitInput: MaterialAutoCompleteTextView
    private lateinit var rememberCheck: CheckBox
    private lateinit var connectButton: MaterialButton
    private lateinit var colorRow: LinearLayout

    private val logLines = mutableListOf<String>()
    private var busy = false
    private var lastAttemptAt = 0L
    private var backgroundColor = Palette.DEFAULT

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        prefs = Prefs(this)

        stateText = findViewById(R.id.stateText)
        detailText = findViewById(R.id.detailText)
        logText = findViewById(R.id.logText)
        accountInput = findViewById(R.id.accountInput)
        passwordInput = findViewById(R.id.passwordInput)
        exitInput = findViewById(R.id.exitInput)
        rememberCheck = findViewById(R.id.rememberCheck)
        connectButton = findViewById(R.id.connectButton)
        colorRow = findViewById(R.id.colorRow)

        backgroundColor = prefs.backgroundColor
        buildSwatches()
        applyBackground(backgroundColor)

        exitInput.setSimpleItems(Accounts.EXITS.map { Accounts.label(it.first) }.toTypedArray())
        accountInput.setText(prefs.username)
        exitInput.setText(Accounts.label(prefs.exitSuffix), false)
        rememberCheck.isChecked = prefs.rememberPassword
        if (prefs.rememberPassword) passwordInput.setText(prefs.password)

        connectButton.setOnClickListener { start() }
        showResult("准备就绪", "正在自动检测校园网…", R.color.text_primary)
    }

    /** 打开、以及从后台切回来时都自动跑一遍；不用手动点。 */
    override fun onStart() {
        super.onStart()
        if (!busy && System.currentTimeMillis() - lastAttemptAt > RETRY_GUARD_MS) {
            start()
        }
    }

    // ------------------------------------------------------------------ 流程

    private fun start() {
        if (busy) return
        lastAttemptAt = System.currentTimeMillis()

        val username = accountInput.text?.toString()?.trim().orEmpty()
        val password = passwordInput.text?.toString().orEmpty()
        val suffix = Accounts.parseSuffix(exitInput.text?.toString().orEmpty())
        val account = Accounts.full(username, suffix)
        val hasCredentials = username.isNotEmpty() && password.isNotEmpty()

        if (hasCredentials) {
            prefs.username = username
            prefs.exitSuffix = suffix
            prefs.rememberPassword = rememberCheck.isChecked
            prefs.password = if (rememberCheck.isChecked) password else ""
        }

        setBusy(true)
        showResult(getString(R.string.status_checking), "正在检测校园网网关…", R.color.text_primary)
        appendLog(if (hasCredentials) "检测 $account" else "还没填账号，先检测网络")

        Thread {
            val outcome = try {
                runFlow(account, password, hasCredentials)
            } catch (error: Exception) {
                Triple(
                    "连接失败",
                    "${error.javaClass.simpleName}：${error.message.orEmpty()}",
                    R.color.state_bad,
                )
            }
            runOnUiThread {
                if (isFinishing || isDestroyed) return@runOnUiThread
                setBusy(false)
                showResult(outcome.first, outcome.second, outcome.third)
            }
        }.start()
    }

    private fun runFlow(
        account: String,
        password: String,
        hasCredentials: Boolean,
    ): Triple<String, String, Int> {
        val network = NetInfo.wifiNetwork(this)
            ?: return Triple("没有连上 WiFi", "请先连接校园网无线，再打开本应用", R.color.state_warn)

        if (NetInfo.hasVpn(this)) appendLog("检测到 VPN，已把请求绑定到无线网卡")

        val probe = Portal.probe(network)
        appendLog("可达网关：" + (probe.reachable.joinToString("、").ifEmpty { "无" }))

        when (probe.state) {
            "offline" -> return Triple(
                "不在校园网",
                "淮南（10.255.0.19）和合肥两个网关都连不上，确认连的是校园网无线",
                R.color.state_warn,
            )
            "online" -> return Triple(
                "已连接",
                "检测到${probe.campus}网关，已通过认证，可以直接上网",
                R.color.state_ok,
            )
        }

        appendLog("需要认证：${probe.campus} ${probe.base}　本机 ${probe.ip.ifBlank { "未知" }}")
        if (!hasCredentials) {
            return Triple(
                "需要账号",
                "已检测到${probe.campus}网关，填上学号和密码，下次打开就会自动连接",
                R.color.state_warn,
            )
        }

        val outcome = Portal.connect(probe.base, account, password, network)
        appendLog(outcome.message)

        return if (outcome.ok) {
            Triple("已连接", "已通过${probe.campus}网关认证", R.color.state_ok)
        } else {
            Triple("连接失败", outcome.message, R.color.state_bad)
        }
    }

    // ------------------------------------------------------------------ 界面

    private fun dp(value: Int): Int = Math.round(value * resources.displayMetrics.density)

    private fun buildSwatches() {
        colorRow.removeAllViews()
        Palette.OPTIONS.forEach { option ->
            val selected = option.color == backgroundColor
            val swatch = View(this)
            val params = LinearLayout.LayoutParams(dp(34), dp(34))
            params.marginEnd = dp(10)
            swatch.layoutParams = params
            swatch.background = swatchDrawable(option.color, selected)
            swatch.contentDescription = option.label + if (selected) "（当前）" else ""
            swatch.setOnClickListener { selectColor(option.color) }
            colorRow.addView(swatch)
        }
    }

    private fun swatchDrawable(color: Int, selected: Boolean): Drawable =
        GradientDrawable().apply {
            shape = GradientDrawable.OVAL
            setColor(color)
            setStroke(
                dp(if (selected) 3 else 1),
                Color.parseColor(if (selected) "#5B8DB8" else "#33000000"),
            )
        }

    private fun selectColor(color: Int) {
        backgroundColor = color
        prefs.backgroundColor = color
        buildSwatches()
        applyBackground(color)
        appendLog("底色换成${Palette.labelOf(color)}")
    }

    private fun applyBackground(color: Int) {
        window.setBackgroundDrawable(ColorDrawable(color))
        window.statusBarColor = color
        window.navigationBarColor = color
    }

    private fun setBusy(value: Boolean) {
        busy = value
        connectButton.isEnabled = !value
        connectButton.setText(if (value) R.string.action_connecting else R.string.action_connect)
    }

    private fun showResult(title: String, detail: String, colorRes: Int) {
        stateText.text = title
        stateText.setTextColor(ContextCompat.getColor(this, colorRes))
        detailText.text = detail
    }

    private fun appendLog(line: String) {
        val stamp = SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(Date())
        runOnUiThread {
            logLines += "[$stamp] $line"
            while (logLines.size > 40) logLines.removeAt(0)
            logText.text = logLines.joinToString("\n")
        }
    }
}
