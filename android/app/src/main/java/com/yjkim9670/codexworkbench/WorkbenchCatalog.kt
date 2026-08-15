package com.yjkim9670.codexworkbench

data class WorkbenchTarget(
    val id: String,
    val name: String,
    val url: String,
)

object WorkbenchCatalog {
    const val DEFAULT_ID = "common_tg"
    const val GATEWAY_ROOT = "https://dinya.wind-mintaka.ts.net"

    val targets = listOf(
        WorkbenchTarget(
            id = "common_tg",
            name = "Common TG Codex Workbench",
            url = "$GATEWAY_ROOT/tg/",
        ),
        WorkbenchTarget(
            id = "finance",
            name = "Finance Codex Workbench",
            url = "$GATEWAY_ROOT/finance-codex/",
        ),
        WorkbenchTarget(
            id = "local",
            name = "Local Codex Workbench",
            url = "$GATEWAY_ROOT/local/",
        ),
        WorkbenchTarget(
            id = "constraint",
            name = "Constraint Codex Workbench",
            url = "$GATEWAY_ROOT/constraint/",
        ),
        WorkbenchTarget(
            id = "dev",
            name = "Dev Codex Workbench",
            url = "$GATEWAY_ROOT/dev/",
        ),
    )

    // Stored preferences from an older app version must never make startup fail.
    fun byId(id: String?): WorkbenchTarget =
        targets.firstOrNull { it.id == id } ?: targets.first()

    fun byUrl(url: String?): WorkbenchTarget? {
        val normalized = url.orEmpty().trim().trimEnd('/')
        return targets.firstOrNull { it.url.trimEnd('/') == normalized }
    }
}
