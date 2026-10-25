# flutter_local_notifications stores scheduled notifications with Gson;
# R8 strips the generic signatures it needs ("Missing type parameter").
-keepattributes Signature
-keep class com.google.gson.reflect.TypeToken { *; }
-keep class * extends com.google.gson.reflect.TypeToken
