plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
}

android {
    namespace = "com.troit.assistant"
    compileSdk {
        version = release(37)
    }

    defaultConfig {
        applicationId = "com.troit.assistant"
        minSdk = 26
        targetSdk = 37
        versionCode = 2
        versionName = "2.0-ecosystem"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"

        // arm64 for phones (Vivo X200 FE), x86_64 for the emulator.
        ndk {
            abiFilters += listOf("arm64-v8a", "x86_64")
        }
    }

    // The Kokoro bundle is stored uncompressed so the first-run copy into
    // app storage is a straight stream copy.
    androidResources {
        noCompress += "litertlm"
    }

    buildTypes {
        release {
            optimization {
                enable = true
                packageScope = setOf("androidx.**", "kotlin.**", "kotlinx.**")
            }
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_11
        targetCompatibility = JavaVersion.VERSION_11
    }
    buildFeatures {
        compose = true
    }
}

dependencies {
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.compose.material3)
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.ui.graphics)
    implementation(libs.androidx.compose.ui.tooling.preview)
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    testImplementation(libs.junit)
    androidTestImplementation(platform(libs.androidx.compose.bom))
    androidTestImplementation(libs.androidx.compose.ui.test.junit4)
    androidTestImplementation(libs.androidx.espresso.core)
    androidTestImplementation(libs.androidx.junit)
    debugImplementation(libs.androidx.compose.ui.test.manifest)
    debugImplementation(libs.androidx.compose.ui.tooling)
    // Kokoro-82M (.litertlm) runs on the MediaPipe Text-to-Speech task (LiteRT-LM backed).
    implementation(libs.mediapipe.tasks.audio)
    implementation(libs.kotlinx.coroutines.android)
    // Freakyyy Link: TLS WebSocket client and QR pairing.
    implementation(libs.okhttp)
    implementation(libs.zxing.android.embedded)
}