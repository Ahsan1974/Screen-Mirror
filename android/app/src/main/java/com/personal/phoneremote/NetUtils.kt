package com.personal.phoneremote

import java.net.Inet4Address
import java.net.InetAddress
import java.net.NetworkInterface

/** LAN address checks. A public source address is rejected so port-forwarding cannot connect. */
object NetUtils {
    fun isPrivate(address: InetAddress): Boolean {
        if (address.isLoopbackAddress || address.isLinkLocalAddress) {
            return true
        }
        if (address is Inet4Address) {
            val bytes = address.address
            val first = bytes[0].toInt() and 0xFF
            val second = bytes[1].toInt() and 0xFF
            if (first == 10) return true
            if (first == 192 && second == 168) return true
            if (first == 172 && second in 16..31) return true
            return false
        }
        return address.isSiteLocalAddress
    }

    fun wifiIpv4(): String {
        val interfaces = NetworkInterface.getNetworkInterfaces() ?: return "unknown"
        var fallback: String? = null
        for (nif in interfaces) {
            if (!nif.isUp || nif.isLoopback) continue
            for (address in nif.inetAddresses) {
                if (address is Inet4Address && isPrivate(address)) {
                    val host = address.hostAddress ?: continue
                    if (nif.name.startsWith("wlan") || nif.name.startsWith("ap")) {
                        return host
                    }
                    if (fallback == null) {
                        fallback = host
                    }
                }
            }
        }
        return fallback ?: "unknown"
    }
}
