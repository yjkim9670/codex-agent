package com.yjkim9670.codexworkbench

object QuickTunnelRetryPolicy {
    private val retryableHttpStatuses = setOf(502, 503, 504)
    private val retryableWebViewErrors = setOf(-2, -6, -7, -8)

    fun shouldRediscoverForHttpStatus(statusCode: Int): Boolean =
        statusCode in retryableHttpStatuses

    fun shouldRediscoverForWebViewError(errorCode: Int): Boolean =
        errorCode in retryableWebViewErrors
}
