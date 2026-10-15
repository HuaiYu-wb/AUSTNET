package top.huaiyu.austnet

import android.graphics.Color

/**
 * 可选底色。
 *
 * 全部是浅色调，这样深色文字在任何一种底色上对比度都够。
 * 想加深色的话，得连带把文字颜色和状态栏图标一起翻转，不能只换背景。
 */
object Palette {

    data class Option(val label: String, val color: Int)

    val OPTIONS: List<Option> = listOf(
        Option("樱粉", Color.parseColor("#FEE7EF")),
        Option("薄荷", Color.parseColor("#E3F5EC")),
        Option("天蓝", Color.parseColor("#E1EFFA")),
        Option("薰衣草", Color.parseColor("#ECE6F8")),
        Option("奶油", Color.parseColor("#FBF2DC")),
        Option("蜜桃", Color.parseColor("#FDE8DC")),
        Option("石墨", Color.parseColor("#ECEEF1")),
        Option("云白", Color.parseColor("#F7F8FA")),
    )

    val DEFAULT: Int = OPTIONS.first().color

    fun labelOf(color: Int): String =
        OPTIONS.firstOrNull { it.color == color }?.label ?: "自定义"
}

