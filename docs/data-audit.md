# Data audit — source `garmin`

Generated 2026-10-01T10:54. Days fetched: 90 (2026-07-04 → 2026-10-01).

## Observations (live, 2026-10-01)

- Daily wellness data present 2026-07-04 → 08-16 and 09-23 → 10-01. **No wellness data 2026-08-17 → 09-22**
  (Garmin returns `includesWellnessData: false`), although runs exist in that period. Stored as `not_measured`.
- Sleep wake-date attribution matched Garmin's `calendarDate` on 7/7 checked nights. Source offset +3 h (IDT).
- Run cadence arrives as total steps/min (~170). Samples every 1–2 s (`maxChartSize` 2000).
- Garmin labels **every** lap `INTERVAL` on recent runs (auto-laps), so this label no longer implies intervals (`running-1.1`).
- 8 of 31 runs are eligible for drift analysis. The rest are under 40 min, so the steady segment after warm-up is < 30 min.
- Training effect / VO₂ max present on 19 of 31 runs (possibly a device difference; not investigated).

## Daily metrics

| Metric | Method | Measured days | Not measured | Coverage |
|---|---|---|---|---|
| active_duration | garmin_active_plus_highly_active | 53 | 37 | 59% |
| avg_stress | garmin_stress | 53 | 37 | 59% |
| body_battery_high | garmin_body_battery | 53 | 37 | 59% |
| body_battery_low | garmin_body_battery | 53 | 37 | 59% |
| garmin_sleep_score | garmin_sleep_score | 44 | 46 | 49% |
| garmin_training_readiness | garmin_morning_readiness | 53 | 37 | 59% |
| garmin_vo2max_running | garmin_vo2max_generic | 19 | 71 | 21% |
| hrv_overnight_avg | garmin_overnight_hrv | 44 | 46 | 49% |
| hrv_weekly_avg | garmin_overnight_hrv_7d | 48 | 42 | 53% |
| respiration_waking_avg | garmin_waking_avg | 53 | 37 | 59% |
| resting_hr | garmin_daily_rhr | 53 | 37 | 59% |
| sleep_duration | garmin_main_sleep | 44 | 46 | 49% |
| steps | garmin_daily_total | 53 | 37 | 59% |
| weight | garmin_weigh_in | 4 | 86 | 4% |

## Activities (31)

| Sport | Count |
|---|---|
| running | 31 |

### Run field presence

| Field | Present |
|---|---|
| distance_m | 31/31 |
| elapsed_s | 31/31 |
| moving_s | 31/31 |
| timer_s | 31/31 |
| avg_hr | 31/31 |
| max_hr | 31/31 |
| elevation_gain_m | 31/31 |
| avg_cadence_spm | 31/31 |
| laps | 31/31 |
| samples | 31/31 |
| samples.hr | 31/31 |
| samples.speed | 31/31 |
| samples.dist | 31/31 |
| samples.elev | 31/31 |
| samples.cad | 31/31 |

### Garmin-generated activity metrics present

- activityTrainingLoad: 31/31
- averageSpeed: 31/31
- maxSpeed: 31/31
- calories: 31/31
- aerobicTrainingEffect: 19/31
- anaerobicTrainingEffect: 19/31
- trainingEffectLabel: 19/31
- vO2MaxValue: 19/31

## Raw payload top-level keys (names only)

- **activity_details** (30 sampled): activityDetailMetrics, activityId, detailsAvailable, geoPolylineDTO, heartRateDTOs, measurementCount, metricDescriptors, metricsCount, pendingData, totalMetricsCount
- **activity_splits** (30 sampled): activityId, eventDTOs, lapDTOs
- **activity_summary** (30 sampled): activityId, activityName, activityTrainingLoad, activityType, activityUUID, aerobicTrainingEffect, aerobicTrainingEffectMessage, anaerobicTrainingEffect, anaerobicTrainingEffectMessage, atpActivity, autoCalcCalories, averageHR, averageRunningCadenceInStepsPerMinute, averageSpeed, avgElevation, avgGradeAdjustedSpeed, avgGroundContactTime, avgPower, avgStrideLength, avgVerticalOscillation, avgVerticalRatio, beginTimestamp, bmrCalories, calories, decoDive, deviceId, differenceBodyBattery, distance, duration, elapsedDuration, elevationCorrected, elevationGain, elevationLoss, endLatitude, endLongitude, endTimeGMT, eventType, fastestSplit_1000, fastestSplit_1609, fastestSplit_5000, favorite, hasHeatMap, hasImages, hasIntensityIntervals, hasPolyline, hasSplits, hasVideo, hrTimeInZone_1, hrTimeInZone_2, hrTimeInZone_3, hrTimeInZone_4, hrTimeInZone_5, isAtpActivity, isAutoCalcCalories, isDecoDive, isElevationCorrected, isFavorite, isManualActivity, isPR, isParent, isPurposeful, lapCount, manualActivity, manufacturer, maxDoubleCadence, maxElevation, maxHR, maxPower, maxRunningCadenceInStepsPerMinute, maxSpeed, maxVerticalSpeed, minActivityLapDuration, minElevation, moderateIntensityMinutes, movingDuration, normPower, ownerDisplayName, ownerFullName, ownerId, ownerProfileImageUrlLarge, ownerProfileImageUrlMedium, ownerProfileImageUrlSmall, parent, powerTimeInZone_1, powerTimeInZone_2, powerTimeInZone_3, powerTimeInZone_4, powerTimeInZone_5, pr, privacy, purposeful, qualifyingDive, splitSummaries, sportTypeId, startLatitude, startLongitude, startTimeGMT, startTimeLocal, steps, summarizedDiveInfo, timeZoneId, trainingEffectLabel, userPro, userRoles, vO2MaxValue, vigorousIntensityMinutes, waterEstimated
- **body_composition** (30 sampled): dateWeightList, endDate, startDate, totalAverage
- **hrv** (30 sampled): endTimestampGMT, endTimestampLocal, hrvReadings, hrvSummary, sleepEndTimestampGMT, sleepEndTimestampLocal, sleepStartTimestampGMT, sleepStartTimestampLocal, startTimestampGMT, startTimestampLocal, userProfilePk
- **max_metrics** (30 sampled): cycling, generic, heatAltitudeAcclimation, userId
- **sleep** (30 sampled): avgOvernightHrv, bodyBatteryChange, breathingDisruptionData, dailySleepDTO, hrvData, hrvStatus, remSleepData, respirationVersion, restingHeartRate, restlessMomentsCount, skinTempDataExists, sleepBodyBattery, sleepHeartRate, sleepLevels, sleepMovement, sleepRestlessMoments, sleepStress, wellnessEpochRespirationAveragesList, wellnessEpochRespirationDataDTOList
- **training_readiness** (30 sampled): acuteLoad, acwrFactorFeedback, acwrFactorPercent, calendarDate, deviceId, feedbackLong, feedbackShort, hrvFactorFeedback, hrvFactorPercent, hrvWeeklyAverage, inputContext, level, primaryActivityTracker, recoveryTime, recoveryTimeChangePhrase, recoveryTimeFactorFeedback, recoveryTimeFactorPercent, score, sleepHistoryFactorFeedback, sleepHistoryFactorPercent, sleepScore, sleepScoreFactorFeedback, sleepScoreFactorPercent, stressHistoryFactorFeedback, stressHistoryFactorPercent, timestamp, timestampLocal, userProfilePK, validSleep
- **user_summary** (30 sampled): abnormalHeartRateAlertsCount, activeKilocalories, activeSeconds, activityStressDuration, activityStressPercentage, averageMonitoringEnvironmentAltitude, averageSpo2, averageStressLevel, avgWakingRespirationValue, bmrKilocalories, bodyBatteryActivityEventList, bodyBatteryAtWakeTime, bodyBatteryChargedValue, bodyBatteryDrainedValue, bodyBatteryDuringSleep, bodyBatteryDynamicFeedbackEvent, bodyBatteryHighestValue, bodyBatteryLowestValue, bodyBatteryMostRecentValue, bodyBatteryVersion, burnedKilocalories, calendarDate, consumedKilocalories, dailyStepGoal, durationInMilliseconds, endOfDayBodyBatteryDynamicFeedbackEvent, floorsAscended, floorsAscendedInMeters, floorsDescended, floorsDescendedInMeters, highStressDuration, highStressPercentage, highestRespirationValue, highlyActiveSeconds, includesActivityData, includesCalorieConsumedData, includesWellnessData, intensityMinutesGoal, lastSevenDaysAvgRestingHeartRate, lastSyncTimestampGMT, latestRespirationTimeGMT, latestRespirationValue, latestSpo2, latestSpo2ReadingTimeGmt, latestSpo2ReadingTimeLocal, lowStressDuration, lowStressPercentage, lowestRespirationValue, lowestSpo2, maxAvgHeartRate, maxHeartRate, maxStressLevel, measurableAsleepDuration, measurableAwakeDuration, mediumStressDuration, mediumStressPercentage, minAvgHeartRate, minHeartRate, moderateIntensityMinutes, netCalorieGoal, netRemainingKilocalories, privacyProtected, remainingKilocalories, respirationAlgorithmVersion, restStressDuration, restStressPercentage, restingCaloriesFromActivity, restingHeartRate, rule, sedentarySeconds, sleepingSeconds, source, stressDuration, stressPercentage, stressQualifier, totalDistanceMeters, totalKilocalories, totalSteps, totalStressDuration, uncategorizedStressDuration, uncategorizedStressPercentage, userDailySummaryId, userFloorsAscendedGoal, userProfileId, uuid, vigorousIntensityMinutes, wellnessActiveKilocalories, wellnessDescription, wellnessDistanceMeters, wellnessEndTimeGmt, wellnessEndTimeLocal, wellnessKilocalories, wellnessStartTimeGmt, wellnessStartTimeLocal
