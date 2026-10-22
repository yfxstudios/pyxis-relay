package com.matthewyak.pyxisviewer

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import android.net.Uri
import android.net.wifi.WifiNetworkSpecifier
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull
import java.net.HttpURLConnection
import java.net.URL
import kotlin.coroutines.resume

/**
 * The link in the relay's QR code:
 *   pyxisviewer://join?ssid=PYXIS-Stream&pass=<Wi-Fi password>&relay=192.168.50.1
 * (made by the relay's settings page; the same link the iPhone app uses).
 */
data class JoinLink(val ssid: String, val password: String, val relay: String) {
    companion object {
        fun parse(uri: Uri?): JoinLink? {
            if (uri == null || uri.scheme?.lowercase() != "pyxisviewer" || uri.host?.lowercase() != "join") return null
            val relay = uri.getQueryParameter("relay") ?: return null
            if (!Regex("^[A-Za-z0-9.\\-:\\[\\]]+$").matches(relay)) return null
            return JoinLink(uri.getQueryParameter("ssid") ?: "", uri.getQueryParameter("pass") ?: "", relay)
        }
    }
}

/** Joins the relay's Wi-Fi for this app. */
object WiFi {
    /** The relay's name on its Wi-Fi (it announces it over mDNS). */
    const val RELAY_NAME = "pyxis-relay.local"

    private var callback: ConnectivityManager.NetworkCallback? = null

    /** Whether the relay answers on the network we're on now (then there's nothing to join). */
    suspend fun relayReachable(relay: String): Boolean = withContext(Dispatchers.IO) {
        runCatching {
            (URL("http://$relay/cgi-bin/pyxis-camera").openConnection() as HttpURLConnection).run {
                connectTimeout = 1500; readTimeout = 1500
                val ok = responseCode in 200..499
                disconnect(); ok
            }
        }.getOrDefault(false)
    }

    /**
     * Asks Android to connect to the network (it shows its own "Connect?" prompt) and routes
     * this app's traffic over it, even though it has no internet. Returns null, or what went
     * wrong. The connection lasts while the app runs; Android remembers the approval.
     */
    suspend fun join(context: Context, ssid: String, password: String): String? {
        val cm = context.getSystemService(ConnectivityManager::class.java)
        callback?.let { runCatching { cm.unregisterNetworkCallback(it) } }
        callback = null
        val spec = WifiNetworkSpecifier.Builder().setSsid(ssid).apply {
            if (password.isNotEmpty()) setWpa2Passphrase(password)
        }.build()
        val request = NetworkRequest.Builder()
            .addTransportType(NetworkCapabilities.TRANSPORT_WIFI)
            .removeCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
            .setNetworkSpecifier(spec)
            .build()
        val result = withTimeoutOrNull(60_000) {
            suspendCancellableCoroutine<String> { cont ->  // "" = joined, else the problem
                val cb = object : ConnectivityManager.NetworkCallback() {
                    override fun onAvailable(network: Network) {
                        cm.bindProcessToNetwork(network)
                        if (cont.isActive) cont.resume("")
                    }
                    override fun onUnavailable() {
                        if (cont.isActive) cont.resume("Couldn't join $ssid (cancelled, or not in range).")
                    }
                    override fun onLost(network: Network) { cm.bindProcessToNetwork(null) }
                }
                callback = cb
                cm.requestNetwork(request, cb)
                cont.invokeOnCancellation { runCatching { cm.unregisterNetworkCallback(cb) } }
            }
        }
        return when (result) {
            null -> "Joining $ssid timed out."
            "" -> null
            else -> result
        }
    }
}
