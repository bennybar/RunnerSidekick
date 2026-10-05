# Add project specific ProGuard rules here.
# You can control the set of applied configuration files using the
# proguardFiles setting in build.gradle.
#
# For more details, see
#   http://developer.android.com/guide/developing/tools/proguard.html

# If your project uses WebView with JS, uncomment the following
# and specify the fully qualified class name to the JavaScript interface
# class:
#-keepclassmembers class fqcn.of.javascript.interface.for.webview {
#   public *;
#}

# Uncomment this to preserve the line number information for
# debugging stack traces.
#-keepattributes SourceFile,LineNumberTable

# If you keep the line number information, uncomment this to
# hide the original source file name.
#-renamesourcefileattribute SourceFile
# ---- Runner Sidekick ----
# Readable stack traces in crash reports
-keepattributes SourceFile,LineNumberTable,*Annotation*,InnerClasses,Signature
-renamesourcefileattribute SourceFile
# kotlinx.serialization: keep the generated serializers of our API models (its own consumer rules cover the library)
-keepclassmembers @kotlinx.serialization.Serializable class com.bennybar.runnersidekick.** {
    *** Companion;
    *** INSTANCE;
    kotlinx.serialization.KSerializer serializer(...);
}
-keep class com.bennybar.runnersidekick.**$$serializer { *; }
-keepclassmembers class com.bennybar.runnersidekick.** { *** Companion; }
