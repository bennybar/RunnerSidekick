package com.bennybar.runnersidekick.data

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.DocumentsContract

/** GTII's export folder, picked once by the runner: the FIT files in it (one per run) for upload. Android keeps this
 *  app's read access to the folder across restarts. */
class FitFolder(context: Context) {
    private val resolver = context.applicationContext.contentResolver

    data class FitFile(val name: String, val size: Long, val uri: Uri)

    /** Keeps the read access the folder picker granted. */
    fun keep(tree: Uri) = resolver.takePersistableUriPermission(tree, Intent.FLAG_GRANT_READ_URI_PERMISSION)

    fun list(tree: Uri): List<FitFile> {
        val children = DocumentsContract.buildChildDocumentsUriUsingTree(tree, DocumentsContract.getTreeDocumentId(tree))
        val cols = arrayOf(DocumentsContract.Document.COLUMN_DOCUMENT_ID, DocumentsContract.Document.COLUMN_DISPLAY_NAME,
            DocumentsContract.Document.COLUMN_SIZE)
        return resolver.query(children, cols, null, null, null)?.use { c ->
            buildList {
                while (c.moveToNext()) {
                    val name = c.getString(1) ?: continue
                    if (name.endsWith(".fit", ignoreCase = true))
                        add(FitFile(name, c.getLong(2), DocumentsContract.buildDocumentUriUsingTree(tree, c.getString(0))))
                }
            }
        }.orEmpty()
    }

    fun read(file: FitFile): ByteArray = resolver.openInputStream(file.uri)?.use { it.readBytes() } ?: ByteArray(0)
}
