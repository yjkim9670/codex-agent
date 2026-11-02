import java.io.File
import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

val signingPropertiesFile = rootProject.file(System.getenv("ANDROID_SIGNING_PROPERTIES") ?: "keystore.properties")
val signingProperties = Properties().apply {
    if (signingPropertiesFile.isFile) signingPropertiesFile.inputStream().use { load(it) }
}
fun signingValue(environment: String, property: String): String =
    System.getenv(environment)?.takeIf { it.isNotBlank() } ?: signingProperties.getProperty(property).orEmpty()
val configuredKeystore = signingValue("ANDROID_KEYSTORE_FILE", "storeFile")
val releaseKeystoreFile = if (configuredKeystore.isBlank()) "" else {
    val candidate = File(configuredKeystore)
    (if (candidate.isAbsolute) candidate else File(signingPropertiesFile.parentFile, configuredKeystore)).absolutePath
}
val releaseKeystorePassword = signingValue("ANDROID_KEYSTORE_PASSWORD", "storePassword")
val releaseKeyAlias = signingValue("ANDROID_KEY_ALIAS", "keyAlias")
val releaseKeyPassword = signingValue("ANDROID_KEY_PASSWORD", "keyPassword")
val releaseSigningConfigured = listOf(
    releaseKeystoreFile,
    releaseKeystorePassword,
    releaseKeyAlias,
    releaseKeyPassword,
).all { it.isNotBlank() } && File(releaseKeystoreFile).isFile
val ciVersionCode = System.getenv("ANDROID_VERSION_CODE")?.toIntOrNull()

android {
    namespace = "com.yjkim9670.codexworkbench"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.yjkim9670.codexworkbench"
        minSdk = 26
        targetSdk = 36
        versionCode = 1_200_000 + (ciVersionCode ?: 0)
        versionName = "1.2.0"
    }

    buildFeatures {
        buildConfig = true
    }

    signingConfigs {
        if (releaseSigningConfigured) {
            create("release") {
                storeFile = file(releaseKeystoreFile)
                storePassword = releaseKeystorePassword
                keyAlias = releaseKeyAlias
                keyPassword = releaseKeyPassword
                enableV1Signing = true
                enableV2Signing = true
                enableV3Signing = true
                enableV4Signing = true
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            if (releaseSigningConfigured) {
                signingConfig = signingConfigs.getByName("release")
            }
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    implementation("androidx.webkit:webkit:1.17.0")
    testImplementation("junit:junit:4.13.2")
}

// Use this task before distributing an APK; unsigned release builds remain available for validation.
tasks.register("requireReleaseSigning") {
    doLast {
        check(releaseSigningConfigured) {
            "Release signing is missing. Configure ANDROID_SIGNING_PROPERTIES or the ANDROID_KEYSTORE_* / ANDROID_KEY_* variables."
        }
    }
}
