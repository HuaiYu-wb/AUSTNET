package top.huaiyu.austnet

/** 账号拼接，和 Windows 版的 appconfig.full_account 保持一致。 */
object Accounts {

    /** 界面上的出口候选项：后缀 -> 显示名 */
    val EXITS: List<Pair<String, String>> = listOf(
        "@unicom" to "联通",
        "@aust" to "电信",
        "@cmcc" to "移动",
        "@jzg" to "教职工",
        "@xyw" to "校园用户",
        "" to "默认（不加后缀）",
    )

    val KNOWN_SUFFIXES: List<String> =
        EXITS.map { it.first }.filter { it.isNotEmpty() } + listOf("@lt", "@dx", "@hfcmcc")

    fun label(suffix: String): String {
        val name = EXITS.firstOrNull { it.first == suffix }?.second
        return if (name != null) "$name（${suffix.ifEmpty { "不加后缀" }}）" else suffix
    }

    /** 从下拉框里的显示文本还原出后缀；用户手填的话原样使用。 */
    fun parseSuffix(text: String): String {
        val value = text.trim()
        EXITS.firstOrNull { value == label(it.first) }?.let { return it.first }
        if (value.isEmpty()) return ""
        return if (value.startsWith("@")) value else "@$value"
    }

    fun full(username: String, suffix: String): String {
        var name = username.trim()
        KNOWN_SUFFIXES.firstOrNull { name.endsWith(it, ignoreCase = true) }?.let {
            name = name.dropLast(it.length)
        }
        return name + suffix
    }
}
