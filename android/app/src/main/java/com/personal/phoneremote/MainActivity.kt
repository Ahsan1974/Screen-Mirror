package com.personal.phoneremote

import android.Manifest
import android.content.Intent
import android.media.projection.MediaProjectionManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.PowerManager
import android.provider.Settings
import android.text.method.ScrollingMovementMethod
import android.view.View
import android.view.inputmethod.InputMethodManager
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.TextView
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.personal.phoneremote.clipboard.ClipboardSync
import com.personal.phoneremote.net.WebHost
import com.personal.phoneremote.input.RemoteAccessibilityService
import com.personal.phoneremote.service.RemoteForegroundService
import com.personal.phoneremote.service.ScreenCaptureService
import com.personal.phoneremote.transfer.prepareOutgoing

class MainActivity : AppCompatActivity() {
    private lateinit var store: DeviceStore
    private lateinit var banner: TextView
    private lateinit var nameInput: EditText
    private lateinit var portInput: EditText
    private lateinit var statusText: TextView
    private lateinit var ipText: TextView
    private lateinit var browserUrl: TextView
    private lateinit var accessibilityStatus: TextView
    private lateinit var pairInput: EditText
    private lateinit var pairButton: Button
    private lateinit var shareButton: Button
    private lateinit var stopShareButton: Button
    private lateinit var transferText: TextView
    private lateinit var logText: TextView

    private val listener: (Snapshot) -> Unit = { snapshot ->
        if (!isDestroyed) render(snapshot)
    }

    private val captureLauncher = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        val data = result.data
        if (result.resultCode != RESULT_OK || data == null) {
            AppState.log("Screen capture was not allowed")
            return@registerForActivityResult
        }
        val intent = Intent(this, ScreenCaptureService::class.java).apply {
            action = ScreenCaptureService.ACTION_START
            putExtra(ScreenCaptureService.EXTRA_RESULT_CODE, result.resultCode)
            putExtra(ScreenCaptureService.EXTRA_DATA, data)
        }
        ContextCompat.startForegroundService(this, intent)
    }

    private val pickFile = registerForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri == null) return@registerForActivityResult
        Thread {
            try {
                val prepared = prepareOutgoing(this, uri)
                val intent = Intent(this, RemoteForegroundService::class.java).apply {
                    action = RemoteForegroundService.ACTION_SEND_FILE
                    putExtra(RemoteForegroundService.EXTRA_PATH, prepared.file.absolutePath)
                    putExtra(RemoteForegroundService.EXTRA_NAME, prepared.name)
                    putExtra(RemoteForegroundService.EXTRA_SIZE, prepared.size)
                    putExtra(RemoteForegroundService.EXTRA_SHA, prepared.sha256)
                }
                runOnUiThread { startService(intent) }
            } catch (_: Exception) {
                AppState.log("Could not read that file. Try choosing it again.")
            }
        }.start()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        store = DeviceStore(this)
        bindViews()
        if (Build.VERSION.SDK_INT >= 33) {
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 100)
        }
        ContextCompat.startForegroundService(this, Intent(this, RemoteForegroundService::class.java))
        AppState.listen(listener)
    }

    override fun onResume() {
        super.onResume()
        val enabled = RemoteAccessibilityService.isEnabled(this) || RemoteAccessibilityService.instance != null
        AppState.update { it.copy(accessibilityEnabled = enabled, localIp = NetUtils.wifiIpv4(), port = store.port) }
    }

    override fun onDestroy() {
        AppState.unlisten(listener)
        super.onDestroy()
    }

    private fun bindViews() {
        banner = findViewById(R.id.banner)
        nameInput = findViewById(R.id.nameInput)
        portInput = findViewById(R.id.portInput)
        statusText = findViewById(R.id.statusText)
        ipText = findViewById(R.id.ipText)
        browserUrl = findViewById(R.id.browserUrl)
        accessibilityStatus = findViewById(R.id.accessibilityStatus)
        pairInput = findViewById(R.id.pairInput)
        pairButton = findViewById(R.id.pairButton)
        shareButton = findViewById(R.id.shareButton)
        stopShareButton = findViewById(R.id.stopShareButton)
        transferText = findViewById(R.id.transferText)
        logText = findViewById(R.id.logText)
        logText.movementMethod = ScrollingMovementMethod()
        nameInput.setText(store.phoneName)
        portInput.setText(store.port.toString())
        nameInput.setOnFocusChangeListener { _, hasFocus -> if (!hasFocus) commitName() }
        portInput.setOnFocusChangeListener { _, hasFocus -> if (!hasFocus) commitPort() }
        pairButton.setOnClickListener { submitCode() }
        shareButton.setOnClickListener { askForCapture() }
        stopShareButton.setOnClickListener {
            ContextCompat.startForegroundService(
                this,
                Intent(this, ScreenCaptureService::class.java).setAction(ScreenCaptureService.ACTION_STOP),
            )
        }
        findViewById<Button>(R.id.accessibilityButton).setOnClickListener {
            startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
            AppState.log("In Accessibility, open Phone Remote and turn it on")
        }
        findViewById<Button>(R.id.keyboardButton).setOnClickListener {
            startActivity(Intent(Settings.ACTION_INPUT_METHOD_SETTINGS))
            AppState.log("Turn on the Phone Remote keyboard, then switch to it")
        }
        findViewById<Button>(R.id.keyboardSwitchButton).setOnClickListener {
            getSystemService(InputMethodManager::class.java).showInputMethodPicker()
        }
        findViewById<Button>(R.id.batteryButton).setOnClickListener { askBattery() }
        findViewById<Button>(R.id.clipboardButton).setOnClickListener { sendClipboard() }
        findViewById<Button>(R.id.fileButton).setOnClickListener { pickFile.launch(arrayOf("*/*")) }
        findViewById<Button>(R.id.forgetButton).setOnClickListener {
            startService(Intent(this, RemoteForegroundService::class.java).setAction(RemoteForegroundService.ACTION_FORGET))
        }
        findViewById<Button>(R.id.quitButton).setOnClickListener {
            stopService(Intent(this, ScreenCaptureService::class.java))
            stopService(Intent(this, RemoteForegroundService::class.java))
            finish()
        }
        val swap = findViewById<CheckBox>(R.id.swapColors)
        swap.isChecked = store.swapRedBlue
        Hub.swapRedBlue = store.swapRedBlue
        swap.setOnCheckedChangeListener { _, checked ->
            store.swapRedBlue = checked
            Hub.swapRedBlue = checked
        }
    }

    private fun render(snapshot: Snapshot) {
        statusText.text = snapshot.statusLine
        ipText.text = "IP: ${snapshot.localIp}    Port: ${snapshot.port}"
        browserUrl.text = if (snapshot.localIp.isNotBlank() && snapshot.localIp != "unknown") {
            "On the other laptop, open\nhttp://${snapshot.localIp}:${WebHost.PORT}"
        } else {
            "Connect Wi-Fi to get the laptop address"
        }
        val accessibilityOn = snapshot.accessibilityEnabled || RemoteAccessibilityService.instance != null
        accessibilityStatus.text = if (accessibilityOn) "Accessibility: on" else "Accessibility: off — touch and typing stay disabled"
        val viewing = snapshot.sharing && snapshot.clientConnected
        banner.visibility = if (viewing) View.VISIBLE else View.GONE
        if (viewing) {
            banner.text = getString(R.string.banner_viewing, snapshot.clientName.ifBlank { "your laptop" })
        }
        pairButton.isEnabled = snapshot.pairingWaiting
        shareButton.isEnabled = !snapshot.sharing
        stopShareButton.isEnabled = snapshot.sharing
        transferText.text = snapshot.transferLine
        logText.text = snapshot.logText
        if (!nameInput.hasFocus() && nameInput.text.toString() != store.phoneName) {
            nameInput.setText(store.phoneName)
        }
        if (!portInput.hasFocus() && portInput.text.toString() != snapshot.port.toString()) {
            portInput.setText(snapshot.port.toString())
        }
    }

    private fun submitCode() {
        val code = pairInput.text.toString().trim()
        if (code.length != 6 || code.any { !it.isDigit() }) {
            AppState.log("Enter the 6-digit code shown on the laptop")
            return
        }
        Hub.server?.submitPairCode(code) ?: AppState.log("The phone service is not running yet")
    }

    private fun askForCapture() {
        val manager = getSystemService(MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
        captureLauncher.launch(manager.createScreenCaptureIntent())
    }

    private fun sendClipboard() {
        val text = ClipboardSync.read(this)
        if (text.isNullOrEmpty()) {
            AppState.log("The clipboard is empty, or Android hid it. Copy text, then tap the button again.")
            return
        }
        Hub.server?.sendClipboardText(text) ?: AppState.log("The phone service is not running yet")
    }

    private fun askBattery() {
        val power = getSystemService(PowerManager::class.java)
        if (power.isIgnoringBatteryOptimizations(packageName)) {
            AppState.log("Background running is already allowed")
            return
        }
        startActivity(
            Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS).apply {
                data = Uri.parse("package:$packageName")
            },
        )
    }

    private fun commitName() {
        store.phoneName = nameInput.text.toString()
        nameInput.setText(store.phoneName)
        startService(Intent(this, RemoteForegroundService::class.java).setAction(RemoteForegroundService.ACTION_READVERTISE))
    }

    private fun commitPort() {
        val port = portInput.text.toString().toIntOrNull()
        if (port == null || port !in 1024..65535) {
            portInput.setText(store.port.toString())
            AppState.log("Use a port from 1024 to 65535")
            return
        }
        if (port == store.port) return
        startService(
            Intent(this, RemoteForegroundService::class.java)
                .setAction(RemoteForegroundService.ACTION_REBIND)
                .putExtra(RemoteForegroundService.EXTRA_PORT, port),
        )
    }
}
