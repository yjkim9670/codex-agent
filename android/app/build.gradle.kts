plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.yjkim9670.codexworkbench"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.yjkim9670.codexworkbench"
        minSdk = 26
        targetSdk = 36
        versionCode = 4
        versionName = "1.1.2"
    }

    buildFeatures {
        buildConfig = true
    }

    buildTypes {
        release {
            isMinifyEnabled = false
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