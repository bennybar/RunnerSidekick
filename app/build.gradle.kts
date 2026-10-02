plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
    alias(libs.plugins.ksp)
}

android {
    namespace = "com.bennybar.runnersidekick"
    compileSdk {
        version = release(37)
    }

    defaultConfig {
        applicationId = "com.bennybar.runnersidekick"
        minSdk = 35
        targetSdk = 36
        versionCode = 32
        versionName = "0.23.0"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        // Google Sign-In: the *Web* OAuth client ID (same value as GOOGLE_WEB_CLIENT_ID in backend/sidekick/config.py).
        buildConfigField("String", "GOOGLE_WEB_CLIENT_ID", "\"\"")
    }

    // Release signing comes from ~/.gradle/gradle.properties (never the repo). Without it, release builds stay unsigned.
    val releaseStore = providers.gradleProperty("RSK_RELEASE_STORE_FILE").orNull
    signingConfigs {
        if (releaseStore != null) {
            create("release") {
                storeFile = file(releaseStore)
                storePassword = providers.gradleProperty("RSK_RELEASE_STORE_PASSWORD").get()
                keyAlias = providers.gradleProperty("RSK_RELEASE_KEY_ALIAS").get()
                keyPassword = providers.gradleProperty("RSK_RELEASE_KEY_PASSWORD").get()
            }
        }
    }

    buildTypes {
        debug {
            // Emulator reaches the host loopback through 10.0.2.2 (see docs/SETUP.md).
            buildConfigField("String", "DEFAULT_BACKEND_URL", "\"http://10.0.2.2:8765\"")
        }
        release {
            isMinifyEnabled = false
            if (releaseStore != null) signingConfig = signingConfigs.getByName("release")
            buildConfigField("String", "DEFAULT_BACKEND_URL", "\"https://runnersidekick.ibarak.org\"")
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }
    testOptions {
        unitTests.isReturnDefaultValues = true
    }
}

ksp {
    arg("room.schemaLocation", "$projectDir/schemas")
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.navigation.compose)
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.ui.tooling.preview)
    implementation(libs.androidx.compose.material3)
    implementation(libs.androidx.compose.material.icons)
    implementation(libs.androidx.graphics.shapes)
    implementation(libs.androidx.credentials)
    implementation(libs.androidx.credentials.play)
    implementation(libs.googleid)
    implementation(libs.androidx.browser)
    implementation(libs.androidx.room.runtime)
    implementation(libs.androidx.room.ktx)
    ksp(libs.androidx.room.compiler)
    implementation(libs.androidx.work.runtime)
    implementation(libs.androidx.datastore.preferences)
    implementation(libs.okhttp)
    implementation(libs.kotlinx.serialization.json)
    debugImplementation(libs.androidx.compose.ui.tooling)
    testImplementation(libs.junit)
    testImplementation(libs.kotlinx.coroutines.test)
    testImplementation(libs.okhttp.mockwebserver)
    androidTestImplementation(libs.androidx.junit)
    androidTestImplementation(libs.androidx.espresso.core)
    androidTestImplementation(libs.androidx.room.testing)
}
