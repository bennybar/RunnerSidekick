package com.bennybar.runnersidekick.data

import android.content.ContentValues
import android.content.Context
import android.os.Environment
import android.provider.MediaStore

/** Files the user keeps, written to the shared Downloads folder through MediaStore (no storage permission needed). */
object Downloads {
    fun saveText(context: Context, fileName: String, mimeType: String, text: String) {
        val resolver = context.contentResolver
        val values = ContentValues().apply {
            put(MediaStore.Downloads.DISPLAY_NAME, fileName)
            put(MediaStore.Downloads.MIME_TYPE, mimeType)
            put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS)
            put(MediaStore.Downloads.IS_PENDING, 1)  // hidden from other apps until fully written
        }
        val uri = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values) ?: error("Couldn't create $fileName in Downloads")
        try {
            resolver.openOutputStream(uri)?.use { it.write(text.toByteArray(Charsets.UTF_8)) } ?: error("Couldn't write $fileName")
            resolver.update(uri, ContentValues().apply { put(MediaStore.Downloads.IS_PENDING, 0) }, null, null)
        } catch (e: Exception) {
            resolver.delete(uri, null, null)
            throw e
        }
    }
}
