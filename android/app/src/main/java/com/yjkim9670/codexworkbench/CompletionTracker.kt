package com.yjkim9670.codexworkbench

/** Baselines old history, tracks fast completions, and requires explicit terminal state. */
internal class CompletionTracker {
    data class Stream(val session: String, val done: Boolean, val cancelled: Boolean = false)
    private var initialized = false
    private val known = mutableSetOf<String>()
    private val pending = linkedMapOf<String, Stream>()
    fun observe(streams: Map<String, Stream>, queue: Int): Set<String> {
        for ((id, stream) in streams) {
            if ((!initialized && !stream.done && !stream.cancelled) || (initialized && id !in known) || id in pending) {
                pending[id] = stream
            }
        }
        known.addAll(streams.keys)
        initialized = true
        if (queue > 0 || pending.isEmpty() || pending.values.any { !it.done && !it.cancelled }) return emptySet()
        val completed = pending.values.filter { it.done && !it.cancelled }.map { it.session }.filter { it.isNotBlank() }.toSet()
        pending.clear()
        return completed
    }
}
