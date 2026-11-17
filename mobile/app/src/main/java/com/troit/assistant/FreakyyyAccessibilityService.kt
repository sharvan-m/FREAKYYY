
package com.troit.assistant

import android.accessibilityservice.AccessibilityService
import android.os.Build
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo

/**
 * Optional, user-enabled automation helper. It only acts when the user asks
 * Freakyyy for something (go home, lock screen, tap a named button, scroll),
 * never reads or stores screen content, skips password fields, and asks
 * for confirmation before tapping anything that looks like a payment,
 * send or delete action.
 *
 * Core Freakyyy features do not depend on this service.
 */
class FreakyyyAccessibilityService : AccessibilityService() {

    override fun onServiceConnected() {
        super.onServiceConnected()
        instance = this
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        // Events are not inspected or recorded.
    }

    override fun onInterrupt() {}

    override fun onDestroy() {
        if (instance === this) instance = null
        super.onDestroy()
    }

    override fun onUnbind(intent: android.content.Intent?): Boolean {
        if (instance === this) instance = null
        return super.onUnbind(intent)
    }

    fun perform(action: FreakyyyGlobalAction): Boolean {
        val id = when (action) {
            FreakyyyGlobalAction.BACK -> GLOBAL_ACTION_BACK
            FreakyyyGlobalAction.HOME -> GLOBAL_ACTION_HOME
            FreakyyyGlobalAction.RECENTS -> GLOBAL_ACTION_RECENTS
            FreakyyyGlobalAction.NOTIFICATIONS -> GLOBAL_ACTION_NOTIFICATIONS
            FreakyyyGlobalAction.QUICK_SETTINGS -> GLOBAL_ACTION_QUICK_SETTINGS
            FreakyyyGlobalAction.SCREENSHOT ->
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) GLOBAL_ACTION_TAKE_SCREENSHOT else return false
            FreakyyyGlobalAction.LOCK_SCREEN ->
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) GLOBAL_ACTION_LOCK_SCREEN else return false
        }
        return performGlobalAction(id)
    }

    enum class TapResult { TAPPED, NOT_FOUND, SENSITIVE, NO_WINDOW }

    /**
     * Taps the first visible element whose text or description contains
     * [label]. Returns SENSITIVE (without tapping) when the element looks
     * like a payment/send/delete control and [confirmed] is false.
     */
    fun tap(label: String, confirmed: Boolean): TapResult {
        val root = rootInActiveWindow ?: return TapResult.NO_WINDOW
        val matches = root.findAccessibilityNodeInfosByText(label)
            .filter { it.isVisibleToUser && !it.isPassword }

        val node = matches.firstOrNull { clickableAncestor(it) != null }
            ?: return TapResult.NOT_FOUND

        val visibleText = listOfNotNull(node.text, node.contentDescription).joinToString(" ")
        if (!confirmed && isSensitive("$label $visibleText")) return TapResult.SENSITIVE

        val target = clickableAncestor(node) ?: return TapResult.NOT_FOUND
        return if (target.performAction(AccessibilityNodeInfo.ACTION_CLICK)) TapResult.TAPPED
        else TapResult.NOT_FOUND
    }

    fun scroll(forward: Boolean): Boolean {
        val root = rootInActiveWindow ?: return false
        val scrollable = findScrollable(root) ?: return false
        return scrollable.performAction(
            if (forward) AccessibilityNodeInfo.ACTION_SCROLL_FORWARD
            else AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD
        )
    }

    private fun clickableAncestor(node: AccessibilityNodeInfo): AccessibilityNodeInfo? {
        var current: AccessibilityNodeInfo? = node
        var depth = 0
        while (current != null && depth < 6) {
            if (current.isClickable && current.isEnabled) return current
            current = current.parent
            depth++
        }
        return null
    }

    private fun findScrollable(node: AccessibilityNodeInfo): AccessibilityNodeInfo? {
        if (node.isScrollable && node.isVisibleToUser) return node
        for (i in 0 until node.childCount) {
            val child = node.getChild(i) ?: continue
            findScrollable(child)?.let { return it }
        }
        return null
    }

    companion object {
        @Volatile
        var instance: FreakyyyAccessibilityService? = null
            private set

        val isRunning: Boolean get() = instance != null

        private val sensitiveWords = Regex(
            """\b(pay|payment|buy|purchase|order|checkout|send|transfer|delete|remove|uninstall|erase|reset|confirm|subscribe|donate|withdraw|sign out|log ?out|password|install)\b""",
            RegexOption.IGNORE_CASE
        )

        fun isSensitive(text: String) = sensitiveWords.containsMatchIn(text)

        /** Lets the user switch the service off from inside Freakyyy. */
        fun disable() {
            instance?.disableSelf()
        }
    }
}
