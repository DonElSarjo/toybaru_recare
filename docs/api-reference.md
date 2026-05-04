# Toyota Connected Europe API Reference (Subaru Solterra)

Auto-generated: 2026-04-17T07:55:40.479519+00:00

## Working Endpoints

| Method | Path | Description | Response Fields |
|--------|------|-------------|-----------------|
| GET | `v2/vehicle/guid` | Vehicle list v2 | alerts, asiCode, brand, capabilities, carlineName, color |
| GET | `v4/account` | Account info | customer |
| GET | `v1/vehicle/electric/status` | Electric status (evcc) | batteryLevel, chargingStatus, evRange, evRangeWithAc, totalRangeWithAc, remainingChargeTime |
| GET | `v1/global/remote/electric/status` | Electric status (old) | batteryLevel, chargingStatus, evRange, evRangeWithAc, remainingChargeTime, lastUpdateTimestamp |
| GET | `v1/location` | Location | vin, lastTimestamp, vehicleLocation |
| GET | `v3/telemetry` | Telemetry v3 | fuelType, odometer, batteryLevel, distanceToEmpty, timestamp, chargingStatus |
| GET | `v1/vehiclehealth/status` | Vehicle health | quantityOfEngOilIcon, warning, vin, wnglastUpdTime |
| GET | `v2/notification/history` | Notifications v2 | notifications |
| GET | `v1/servicehistory/vehicle/summary` | Service history | serviceHistories |
| GET | `v1/global/remote/climate-status` | Climate status | type, status |
| GET | `v1/global/remote/climate-settings` | Climate settings | temperature, temperatureUnit, minTemp, maxTemp, tempInterval, acOperations |
| GET | `v1/trips/a75f3707-b27c-4503-a2b5-7559942b1a75` | trip (base) | id, processedIn, summary, scores, behaviours, hdc |

## Forbidden Endpoints (403 - Gateway Block)

- `v1/charging/history` 
- `v1/consumption` 
- `v1/drivePulse` 
- `v1/electricPulse` 
- `v1/global/remote/electric/command` 
- `v1/global/remote/electric/realtime-status` 
- `v1/global/remote/engine-status` 
- `v1/global/remote/refresh-climate-status` 
- `v1/global/remote/status` 
- `v1/notification/history` 
- `v1/telemetry` 
- `v1/trips/a75f3707-b27c-4503-a2b5-7559942b1a75/analysis` 
- `v1/trips/a75f3707-b27c-4503-a2b5-7559942b1a75/behaviours` 
- `v1/trips/a75f3707-b27c-4503-a2b5-7559942b1a75/details` 
- `v1/trips/a75f3707-b27c-4503-a2b5-7559942b1a75/energy` 
- `v1/trips/a75f3707-b27c-4503-a2b5-7559942b1a75/hdc` 
- `v1/trips/a75f3707-b27c-4503-a2b5-7559942b1a75/route` 
- `v1/trips/a75f3707-b27c-4503-a2b5-7559942b1a75/scores` 
- `v1/trips/a75f3707-b27c-4503-a2b5-7559942b1a75/statistics` 
- `v1/trips/a75f3707-b27c-4503-a2b5-7559942b1a75/summary` 
- `v1/vehicle-association/vehicle` 
- `v1/vehicle/charging` 
- `v1/vehicle/diagnostic` 
- `v1/vehicle/diagnostics` 
- `v1/vehicle/drivePulse` 
- `v1/vehicle/electric/charging-history` 
- `v1/vehicle/electricPulse` 
- `v1/vehicle/energy` 
- `v1/vehicle/guid` 
- `v2/drivePulse` 
- `v2/electricPulse` 
- `v2/location` 
- `v2/telemetry` 
- `v2/vehicle/diagnostic` 
- `v2/vehicle/energy` 
- `v2/vehiclehealth/status` 
- `v3/electricPulse` 
- `v3/location` 
- `v3/notification/history` 
- `v3/vehicle/guid` 
- `v4/vehicle/guid` 

## Trip Summary Field Analysis

Testing different query parameters to find hidden fields:

### route=false summary=false
- Trips: 1, Route points: 0, Behaviours: 5
- Summary keys: `['averageSpeed', 'duration', 'endLat', 'endLon', 'endTs', 'fuelConsumption', 'length', 'nightTrip', 'startLat', 'startLon', 'startTs']`
- Top keys: `['behaviours', 'category', 'hdc', 'id', 'processedIn', 'scores', 'summary']`

### route=true summary=false
- Trips: 1, Route points: 1776, Behaviours: 5
- Summary keys: `['averageSpeed', 'duration', 'endLat', 'endLon', 'endTs', 'fuelConsumption', 'length', 'nightTrip', 'startLat', 'startLon', 'startTs']`
- Top keys: `['behaviours', 'category', 'hdc', 'id', 'processedIn', 'route', 'scores', 'summary']`
- Route point keys: `['highway', 'indexInPoints', 'isEv', 'lat', 'lon', 'mode', 'overspeed']`

### route=false summary=true
- Trips: 1, Route points: 0, Behaviours: 5
- Summary keys: `['averageSpeed', 'duration', 'endLat', 'endLon', 'endTs', 'fuelConsumption', 'length', 'nightTrip', 'startLat', 'startLon', 'startTs']`
- Top keys: `['behaviours', 'category', 'hdc', 'id', 'processedIn', 'scores', 'summary']`

### route=true summary=true
- Trips: 1, Route points: 1776, Behaviours: 5
- Summary keys: `['averageSpeed', 'duration', 'endLat', 'endLon', 'endTs', 'fuelConsumption', 'length', 'nightTrip', 'startLat', 'startLon', 'startTs']`
- Top keys: `['behaviours', 'category', 'hdc', 'id', 'processedIn', 'route', 'scores', 'summary']`
- Route point keys: `['highway', 'indexInPoints', 'isEv', 'lat', 'lon', 'mode', 'overspeed']`

### electricPulse=true
- Trips: 1, Route points: 1776, Behaviours: 5
- Summary keys: `['averageSpeed', 'duration', 'endLat', 'endLon', 'endTs', 'fuelConsumption', 'length', 'nightTrip', 'startLat', 'startLon', 'startTs']`
- Top keys: `['behaviours', 'category', 'hdc', 'id', 'processedIn', 'route', 'scores', 'summary']`
- Route point keys: `['highway', 'indexInPoints', 'isEv', 'lat', 'lon', 'mode', 'overspeed']`

### include=all
- Trips: 1, Route points: 1776, Behaviours: 5
- Summary keys: `['averageSpeed', 'duration', 'endLat', 'endLon', 'endTs', 'fuelConsumption', 'length', 'nightTrip', 'startLat', 'startLon', 'startTs']`
- Top keys: `['behaviours', 'category', 'hdc', 'id', 'processedIn', 'route', 'scores', 'summary']`
- Route point keys: `['highway', 'indexInPoints', 'isEv', 'lat', 'lon', 'mode', 'overspeed']`

### detail=full
- Trips: 1, Route points: 1776, Behaviours: 5
- Summary keys: `['averageSpeed', 'duration', 'endLat', 'endLon', 'endTs', 'fuelConsumption', 'length', 'nightTrip', 'startLat', 'startLon', 'startTs']`
- Top keys: `['behaviours', 'category', 'hdc', 'id', 'processedIn', 'route', 'scores', 'summary']`
- Route point keys: `['highway', 'indexInPoints', 'isEv', 'lat', 'lon', 'mode', 'overspeed']`

### verbose=true
- Trips: 1, Route points: 1776, Behaviours: 5
- Summary keys: `['averageSpeed', 'duration', 'endLat', 'endLon', 'endTs', 'fuelConsumption', 'length', 'nightTrip', 'startLat', 'startLon', 'startTs']`
- Top keys: `['behaviours', 'category', 'hdc', 'id', 'processedIn', 'route', 'scores', 'summary']`
- Route point keys: `['highway', 'indexInPoints', 'isEv', 'lat', 'lon', 'mode', 'overspeed']`

### fields=maxSpeed,countries,overspeed
- Trips: 1, Route points: 1776, Behaviours: 5
- Summary keys: `['averageSpeed', 'duration', 'endLat', 'endLon', 'endTs', 'fuelConsumption', 'length', 'nightTrip', 'startLat', 'startLon', 'startTs']`
- Top keys: `['behaviours', 'category', 'hdc', 'id', 'processedIn', 'route', 'scores', 'summary']`
- Route point keys: `['highway', 'indexInPoints', 'isEv', 'lat', 'lon', 'mode', 'overspeed']`

### expand=all
- Trips: 1, Route points: 1776, Behaviours: 5
- Summary keys: `['averageSpeed', 'duration', 'endLat', 'endLon', 'endTs', 'fuelConsumption', 'length', 'nightTrip', 'startLat', 'startLon', 'startTs']`
- Top keys: `['behaviours', 'category', 'hdc', 'id', 'processedIn', 'route', 'scores', 'summary']`
- Route point keys: `['highway', 'indexInPoints', 'isEv', 'lat', 'lon', 'mode', 'overspeed']`

### version=2
- Trips: 1, Route points: 1776, Behaviours: 5
- Summary keys: `['averageSpeed', 'duration', 'endLat', 'endLon', 'endTs', 'fuelConsumption', 'length', 'nightTrip', 'startLat', 'startLon', 'startTs']`
- Top keys: `['behaviours', 'category', 'hdc', 'id', 'processedIn', 'route', 'scores', 'summary']`
- Route point keys: `['highway', 'indexInPoints', 'isEv', 'lat', 'lon', 'mode', 'overspeed']`

### OLD trip Oct 2025
- Trips: 1, Route points: 139, Behaviours: 3
- Summary keys: `['averageSpeed', 'duration', 'endLat', 'endLon', 'endTs', 'fuelConsumption', 'length', 'nightTrip', 'startLat', 'startLon', 'startTs']`
- Top keys: `['behaviours', 'category', 'hdc', 'id', 'processedIn', 'route', 'scores', 'summary']`
- Route point keys: `['highway', 'indexInPoints', 'isEv', 'lat', 'lon', 'mode', 'overspeed']`


## Endpoint Response Schemas

### `GET v4/account`
_Account info_

| Field | Type | Details |
|-------|------|---------|
| `customer` | object | keys: ['accountStatus', 'additionalAttributes', 'countryOfResidence', 'createDate', 'createSource', 'customerType', 'emails', 'firstName'] |

### `GET v1/vehicle/electric/status`
_Electric status (evcc)_

| Field | Type | Details |
|-------|------|---------|
| `batteryLevel` | int | 57 |
| `chargingStatus` | str | charging |
| `evRange` | object | keys: ['unit', 'value'] |
| `evRangeWithAc` | object | keys: ['unit', 'value'] |
| `totalRangeWithAc` | object | keys: ['unit', 'value'] |
| `remainingChargeTime` | int | 670 |
| `lastUpdateTimestamp` | str | 2026-04-17T07:46:31Z |
| `dcmTimestamp` | str | 2026-04-17T07:46:27Z |

### `GET v1/global/remote/electric/status`
_Electric status (old)_

| Field | Type | Details |
|-------|------|---------|
| `batteryLevel` | int | 57 |
| `chargingStatus` | str | charging |
| `evRange` | object | keys: ['unit', 'value'] |
| `evRangeWithAc` | object | keys: ['unit', 'value'] |
| `remainingChargeTime` | int | 670 |
| `lastUpdateTimestamp` | str | 2026-04-17T07:46:27Z |

### `GET v1/location`
_Location_

| Field | Type | Details |
|-------|------|---------|
| `vin` | str | JF1AABAA9PA006121 |
| `lastTimestamp` | str | 2026-04-17T07:11:01Z |
| `vehicleLocation` | object | keys: ['displayName', 'latitude', 'locationAcquisitionDatetime', 'longitude'] |

### `GET v3/telemetry`
_Telemetry v3_

| Field | Type | Details |
|-------|------|---------|
| `fuelType` | str | E |
| `odometer` | object | keys: ['unit', 'value'] |
| `batteryLevel` | int | 57 |
| `distanceToEmpty` | object | keys: ['unit', 'value'] |
| `timestamp` | str | 2026-04-17T07:46:27Z |
| `chargingStatus` | str | charging |

### `GET v1/vehiclehealth/status`
_Vehicle health_

| Field | Type | Details |
|-------|------|---------|
| `quantityOfEngOilIcon` | list[0] |  |
| `warning` | list[0] |  |
| `vin` | str | JF1AABAA9PA006121 |
| `wnglastUpdTime` | str | 2026-04-17T07:55:45.810Z |

### `GET v1/servicehistory/vehicle/summary`
_Service history_

| Field | Type | Details |
|-------|------|---------|
| `serviceHistories` | list[0] |  |

### `GET v1/global/remote/climate-status`
_Climate status_

| Field | Type | Details |
|-------|------|---------|
| `type` | str | full |
| `status` | int | 0 |

### `GET v1/global/remote/climate-settings`
_Climate settings_

| Field | Type | Details |
|-------|------|---------|
| `temperature` | float | 18.0 |
| `temperatureUnit` | str | C |
| `minTemp` | float | 18.0 |
| `maxTemp` | float | 29.0 |
| `tempInterval` | float | 1.0 |
| `acOperations` | list[3] | items: ['acParameters', 'available', 'categoryDisplayName', 'categoryName'] |
| `settingsOn` | bool | True |

### `GET v1/trips/a75f3707-b27c-4503-a2b5-7559942b1a75`
_trip (base)_

| Field | Type | Details |
|-------|------|---------|
| `id` | str | a75f3707-b27c-4503-a2b5-7559942b1a75 |
| `processedIn` | int | 10 |
| `summary` | object | keys: ['averageSpeed', 'duration', 'endLat', 'endLon', 'endTs', 'fuelConsumption', 'length', 'nightTrip'] |
| `scores` | object | keys: ['acceleration', 'advice', 'braking', 'constantSpeed', 'global'] |
| `behaviours` | list[5] | items: ['coachingMsg', 'context', 'diagnosticMsg', 'good', 'lat', 'location', 'lon', 'priority'] |
| `hdc` | object | keys: ['chargeDist', 'chargeTime', 'ecoDist', 'ecoTime', 'evDistance', 'evTime', 'powerDist', 'powerTime'] |
| `category` | int | 0 |
| `route` | list[1776] | items: ['highway', 'indexInPoints', 'isEv', 'lat', 'lon', 'mode', 'overspeed'] |
| `createdOn` | str | 2026-04-17T07:10:11Z |


## Bruteforce Discovery

Additional endpoints found:

- `v1/trips`: ['trips', '_metadata']
- `v1/location`: ['vin', 'lastTimestamp', 'vehicleLocation']
- `v1/odometer`: ['mileage', 'timestamp', 'lastUpdateTimestamp', 'isValidTimestamp']
- `v3/telemetry`: ['fuelType', 'odometer', 'batteryLevel', 'distanceToEmpty', 'timestamp']
- `v4/account`: ['customer']
- `v1/vehicle/status`: ['vin', 'lastUpdateTimestamp', 'overallStatus', 'overallWarningCounts', 'leftHandDrive']
- `v1/global/remote/status`: ['vehicleStatus', 'telemetry', 'occurrenceDate', 'cautionOverallCount', 'latitude']