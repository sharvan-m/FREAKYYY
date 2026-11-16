
package com.troit.assistant

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID

/**
 * A routine is an ordered list of ordinary Freakyyy commands
 * ("turn on do not disturb", "wait 3 seconds", "open youtube").
 * Any command Freakyyy understands can be a step, so routines grow with the
 * command engine instead of needing their own action types.
 */
data class FreakyyyRoutine(
    val id: String = UUID.randomUUID().toString(),
    val name: String,
    val steps: List<String>
)

class FreakyyyRoutineStore(context: Context) {

    private val prefs = context.applicationContext
        .getSharedPreferences("dexter_routines", Context.MODE_PRIVATE)

    fun all(): List<FreakyyyRoutine> {
        val raw = prefs.getString(KEY, null) ?: return defaults().also { save(it) }
        return try {
            val array = JSONArray(raw)
            (0 until array.length()).map { i ->
                val o = array.getJSONObject(i)
                val steps = o.getJSONArray("steps")
                FreakyyyRoutine(
                    id = o.getString("id"),
                    name = o.getString("name"),
                    steps = (0 until steps.length()).map { steps.getString(it) }
                )
            }
        } catch (_: Exception) {
            defaults()
        }
    }

    fun save(routines: List<FreakyyyRoutine>) {
        val array = JSONArray()
        routines.forEach { r ->
            array.put(
                JSONObject()
                    .put("id", r.id)
                    .put("name", r.name)
                    .put("steps", JSONArray(r.steps))
            )
        }
        prefs.edit().putString(KEY, array.toString()).apply()
    }

    fun upsert(routine: FreakyyyRoutine) {
        val list = all().toMutableList()
        val index = list.indexOfFirst { it.id == routine.id }
        if (index >= 0) list[index] = routine else list += routine
        save(list)
    }

    fun delete(id: String) = save(all().filterNot { it.id == id })

    /** "study", "my study", "study routine" all find "Study". */
    fun find(name: String): FreakyyyRoutine? {
        val key = name.lowercase()
            .removePrefix("my ")
            .removeSuffix(" routine")
            .removeSuffix(" mode")
            .trim()
        val routines = all()
        return routines.firstOrNull { it.name.lowercase() == key }
            ?: routines.firstOrNull { it.name.lowercase().removeSuffix(" routine") == key }
            ?: routines.firstOrNull { key.contains(it.name.lowercase()) || it.name.lowercase().contains(key) }
    }

    private fun defaults() = listOf(
        FreakyyyRoutine(
            name = "Study",
            steps = listOf(
                "turn on do not disturb",
                "set media volume to 30 percent",
                "set brightness to 60 percent"
            )
        ),
        FreakyyyRoutine(
            name = "Sleep",
            steps = listOf(
                "set brightness to 10 percent",
                "set media volume to 0 percent",
                "turn on do not disturb",
                "turn on dark theme"
            )
        ),
        FreakyyyRoutine(
            name = "Work",
            steps = listOf(
                "turn off do not disturb",
                "set ring volume to 70 percent",
                "open calendar"
            )
        )
    )

    private companion object {
        const val KEY = "routines_v1"
    }
}

// =====================================================
// HISTORY
// =====================================================

data class FreakyyyHistoryEntry(
    val time: Long,
    val command: String,
    val action: String,
    val outcome: Outcome,
    val result: String
)

/**
 * Local, app-private record of commands and their outcomes. Only the
 * command text and Freakyyy's own reply are stored — never screen or
 * notification content.
 */
class FreakyyyHistoryStore(context: Context) {

    private val prefs = context.applicationContext
        .getSharedPreferences("dexter_history", Context.MODE_PRIVATE)

    fun all(): List<FreakyyyHistoryEntry> {
        val raw = prefs.getString(KEY, null) ?: return emptyList()
        return try {
            val array = JSONArray(raw)
            (0 until array.length()).map { i ->
                val o = array.getJSONObject(i)
                FreakyyyHistoryEntry(
                    time = o.getLong("t"),
                    command = o.getString("c"),
                    action = o.getString("a"),
                    outcome = runCatching { Outcome.valueOf(o.getString("o")) }.getOrDefault(Outcome.INFO),
                    result = o.getString("r")
                )
            }
        } catch (_: Exception) {
            emptyList()
        }
    }

    fun add(entry: FreakyyyHistoryEntry) {
        val list = (listOf(entry) + all()).take(MAX)
        val array = JSONArray()
        list.forEach {
            array.put(
                JSONObject()
                    .put("t", it.time)
                    .put("c", it.command.take(200))
                    .put("a", it.action)
                    .put("o", it.outcome.name)
                    .put("r", it.result.take(300))
            )
        }
        prefs.edit().putString(KEY, array.toString()).apply()
    }

    fun clear() = prefs.edit().remove(KEY).apply()

    private companion object {
        const val KEY = "history_v1"
        const val MAX = 150
    }
}
