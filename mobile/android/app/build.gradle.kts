plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "ru.neurogazette.neurowatchconnect"
    compileSdk = 35

    defaultConfig {
        applicationId = "ru.neurogazette.neurowatchconnect"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "0.9"
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
    testImplementation("junit:junit:4.13.2")
}
