package top.huaiyu.austnet

import android.content.Context

/** 账号、出口等设置；密码经 SecretStore 加密后存放。 */
class Prefs(context: Context) {

    private val store = context.applicationContext
        .getSharedPreferences("austnet", Context.MODE_PRIVATE)

    var username: String
        get() = store.getString("username", "").orEmpty()
        set(value) = store.edit().putString("username", value).apply()

    var exitSuffix: String
        get() = store.getString("exit", "@unicom").orEmpty()
        set(value) = store.edit().putString("exit", value).apply()

    var rememberPassword: Boolean
        get() = store.getBoolean("remember", true)
        set(value) = store.edit().putBoolean("remember", value).apply()

    var backgroundColor: Int
        get() = store.getInt("background", Palette.DEFAULT)
        set(value) = store.edit().putInt("background", value).apply()

    var password: String
        get() {
            val saved = store.getString("password", "").orEmpty()
            return if (saved.isEmpty()) "" else SecretStore.decrypt(saved).orEmpty()
        }
        set(value) {
            if (value.isEmpty()) {
                store.edit().remove("password").apply()
            } else {
                store.edit().putString("password", SecretStore.encrypt(value)).apply()
            }
        }
}
