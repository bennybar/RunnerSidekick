package com.bennybar.runnersidekick.data.local

import android.content.Context
import androidx.room.ColumnInfo
import androidx.room.Dao
import androidx.room.Database
import androidx.room.Entity
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.PrimaryKey
import androidx.room.Query
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.room.Upsert
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase
import kotlinx.coroutines.flow.Flow

/**
 * Offline cache. Every row records the backend [mode] it came from ("garmin" or "fixture"), and the
 * repository clears the cache when the mode changes, so synthetic and live data never mix.
 */
@Entity(tableName = "cached_blob")
data class CachedBlob(
    @PrimaryKey val key: String,        // e.g. "status", "today:2026-10-01", "activities", "activity:<id>"
    val mode: String,
    val json: String,
    val fetchedAt: Long,
)

@Entity(tableName = "report")
data class ReportEntity(
    @PrimaryKey val id: Long,           // backend report id (one per revision)
    val type: String,
    val subjectKey: String,
    val localDate: String,
    val revision: Int,
    val title: String?,
    val state: String?,
    val mode: String,
    val json: String?,                  // full body once opened or prefetched
    val fetchedAt: Long,
)

/** Check-ins are written here first and pushed later. Conflict policy (backend): last clientUpdatedAt wins. */
@Entity(tableName = "checkin")
data class CheckinEntity(
    @PrimaryKey val id: String,
    val localDate: String,
    val energy: Int?,
    val soreness: Int?,
    val recovery: Int?,
    val pain: Boolean,
    val illness: Boolean,
    val notes: String?,
    val tagsJson: String,
    val clientUpdatedAt: String,
    val pendingSync: Boolean,
    /** Account that owns this check-in ("<backend url>#<user id>"); "" = written before accounts existed. */
    @ColumnInfo(defaultValue = "") val account: String = "",
)

@Dao
interface CacheDao {
    @Query("SELECT * FROM cached_blob WHERE `key` = :key AND mode = :mode")
    fun observe(key: String, mode: String): Flow<CachedBlob?>

    @Query("SELECT * FROM cached_blob WHERE `key` = :key")
    suspend fun get(key: String): CachedBlob?

    @Upsert
    suspend fun put(blob: CachedBlob)

    @Query("DELETE FROM cached_blob WHERE mode != :mode")
    suspend fun deleteOtherModes(mode: String)

    @Query("DELETE FROM cached_blob")
    suspend fun clear()

    /** Per-run and per-day copies not opened for a while (the main screens' copies are kept, always fresh) */
    @Query("DELETE FROM cached_blob WHERE fetchedAt < :before AND (`key` LIKE 'activity:%' OR `key` LIKE 'runai:%' OR `key` LIKE 'day:%' OR `key` LIKE 'trends:%')")
    suspend fun pruneOld(before: Long)
}

@Dao
interface ReportDao {
    /** Latest revision per report; older revisions stay cached so a report opened offline shows what was known then. */
    @Query(
        "SELECT * FROM report r WHERE mode = :mode AND revision = (SELECT MAX(revision) FROM report x " +
            "WHERE x.type = r.type AND x.subjectKey = r.subjectKey AND x.mode = r.mode) ORDER BY localDate DESC, id DESC"
    )
    fun observeAll(mode: String): Flow<List<ReportEntity>>

    @Query("SELECT * FROM report WHERE id = :id")
    fun observe(id: Long): Flow<ReportEntity?>

    @Query("SELECT * FROM report WHERE id = :id")
    suspend fun get(id: Long): ReportEntity?

    @Upsert
    suspend fun upsert(r: ReportEntity)

    @Query("DELETE FROM report WHERE mode != :mode")
    suspend fun deleteOtherModes(mode: String)

    @Query("DELETE FROM report")
    suspend fun clear()
}

@Dao
interface CheckinDao {
    @Query("SELECT * FROM checkin WHERE localDate = :date AND account = :account ORDER BY clientUpdatedAt DESC LIMIT 1")
    fun observeForDate(date: String, account: String): Flow<CheckinEntity?>

    @Query("SELECT * FROM checkin WHERE account = :account ORDER BY localDate DESC")
    fun observeAll(account: String): Flow<List<CheckinEntity>>

    /** Only the signed-in account's unsent check-ins are ever uploaded. */
    @Query("SELECT * FROM checkin WHERE pendingSync = 1 AND account = :account")
    suspend fun pending(account: String): List<CheckinEntity>

    /** Check-ins written before accounts existed belong to the first account that signs in after the upgrade. */
    @Query("UPDATE checkin SET account = :account WHERE account = ''")
    suspend fun adoptLegacy(account: String)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun put(c: CheckinEntity)

    @Query("SELECT * FROM checkin WHERE id = :id")
    suspend fun get(id: String): CheckinEntity?

    @Query("DELETE FROM checkin WHERE id = :id")
    suspend fun delete(id: String)

    @Query("UPDATE checkin SET pendingSync = 0 WHERE id = :id AND clientUpdatedAt = :clientUpdatedAt")
    suspend fun markSynced(id: String, clientUpdatedAt: String)

    @Query("DELETE FROM checkin")
    suspend fun clear()
}

@Database(entities = [CachedBlob::class, ReportEntity::class, CheckinEntity::class], version = 2, exportSchema = true)
abstract class SidekickDb : RoomDatabase() {
    abstract fun cache(): CacheDao
    abstract fun reports(): ReportDao
    abstract fun checkins(): CheckinDao

    companion object {
        fun create(context: Context): SidekickDb =
            Room.databaseBuilder(context, SidekickDb::class.java, "sidekick.db").addMigrations(MIGRATION_1_2).build()

        /** v2: check-ins get an owning account. */
        val MIGRATION_1_2 = object : Migration(1, 2) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL("ALTER TABLE checkin ADD COLUMN account TEXT NOT NULL DEFAULT ''")
            }
        }
    }
}
