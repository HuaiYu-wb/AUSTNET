package top.huaiyu.austnet

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities

/**
 * 网络探测。
 *
 * 关键点：后面的 HTTP 请求会绑定到这里返回的 WiFi [Network] 上，
 * 这样就算手机同时插着卡、或者开着 VPN，请求也会从无线网卡发出去。
 */
object NetInfo {

    // allNetworks 在新版本里被标记为废弃，但它正好是我们要的"同步拿一份快照"，
    // 替代方案只有注册回调再自己维护列表，对这个一次性动作来说没必要。
    @Suppress("DEPRECATION")
    fun wifiNetwork(context: Context): Network? {
        val manager = context.getSystemService(ConnectivityManager::class.java) ?: return null
        return manager.allNetworks.firstOrNull { network ->
            manager.getNetworkCapabilities(network)
                ?.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) == true
        }
    }

    @Suppress("DEPRECATION")
    fun hasVpn(context: Context): Boolean {
        val manager = context.getSystemService(ConnectivityManager::class.java) ?: return false
        return manager.allNetworks.any { network ->
            manager.getNetworkCapabilities(network)
                ?.hasTransport(NetworkCapabilities.TRANSPORT_VPN) == true
        }
    }
}
