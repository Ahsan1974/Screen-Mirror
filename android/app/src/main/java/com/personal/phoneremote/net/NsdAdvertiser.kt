package com.personal.phoneremote.net

import android.content.Context
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import com.personal.phoneremote.AppState

/** Advertise _ahsanremote._tcp so the laptop can find this phone with zeroconf. */
class NsdAdvertiser(context: Context) {
    private val nsd = context.applicationContext.getSystemService(NsdManager::class.java)
    private var listener: NsdManager.RegistrationListener? = null

    fun register(name: String, port: Int, phoneId: String) {
        unregister()
        val info = NsdServiceInfo().apply {
            serviceName = name.ifBlank { "Android phone" }.take(40)
            serviceType = SERVICE_TYPE
            this.port = port
        }
        info.setAttribute("id", phoneId)
        info.setAttribute("name", name)
        val registration = object : NsdManager.RegistrationListener {
            override fun onServiceRegistered(serviceInfo: NsdServiceInfo) {
                AppState.log("Visible on Wi-Fi as ${serviceInfo.serviceName}")
            }

            override fun onRegistrationFailed(serviceInfo: NsdServiceInfo, errorCode: Int) {
                AppState.log("Could not advertise on Wi-Fi (error $errorCode). Connect with the IP address instead.")
            }

            override fun onServiceUnregistered(serviceInfo: NsdServiceInfo) = Unit

            override fun onUnregistrationFailed(serviceInfo: NsdServiceInfo, errorCode: Int) = Unit
        }
        listener = registration
        try {
            nsd.registerService(info, NsdManager.PROTOCOL_DNS_SD, registration)
        } catch (error: Exception) {
            AppState.log("Could not advertise on Wi-Fi. Connect with the IP address instead.")
        }
    }

    fun unregister() {
        val current = listener ?: return
        listener = null
        try {
            nsd.unregisterService(current)
        } catch (_: Exception) {
        }
    }

    companion object {
        const val SERVICE_TYPE = "_ahsanremote._tcp"
    }
}
