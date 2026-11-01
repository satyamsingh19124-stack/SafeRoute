
# from flask import Flask, render_template, request, jsonify
# from urllib.request import Request, urlopen
# from urllib.error import URLError, HTTPError
# from urllib.parse import urlencode
# import json
# import time

# app = Flask(__name__)

# # Cache place-search results to reduce repeated requests.
# place_cache = {}
# last_search_time = 0


# def search_places(query):
#     """Find matching places in India."""
#     global last_search_time

#     query = query.strip()

#     if not query:
#         return []

#     cache_key = query.lower()

#     if cache_key in place_cache:
#         return place_cache[cache_key]

#     elapsed = time.monotonic() - last_search_time
#     if elapsed < 1.1:
#         time.sleep(1.1 - elapsed)

#     params = urlencode({
#         "q": query,
#         "format": "jsonv2",
#         "limit": 5,
#         "countrycodes": "in",
#         "addressdetails": 1
#     })

#     url = "https://nominatim.openstreetmap.org/search?" + params

#     req = Request(
#         url,
#         headers={
#             "User-Agent": "SafeRouteStudentProject/1.0 (educational demo)"
#         }
#     )

#     with urlopen(req, timeout=15) as response:
#         data = json.loads(response.read().decode("utf-8"))

#     last_search_time = time.monotonic()

#     results = []

#     for item in data:
#         results.append({
#             "name": item.get("display_name", query),
#             "lat": float(item["lat"]),
#             "lon": float(item["lon"])
#         })

#     place_cache[cache_key] = results
#     return results



# def calculate_safety(route_geometry, distance_m=0):
#     """
#     Estimate support along a route using mapped police stations and hospitals
#     within 500 metres of the route. This is a prototype index, not a verified
#     crime/safety rating; OpenStreetMap data may be incomplete.
#     """
#     import math

#     coordinates = route_geometry.get("coordinates", [])
#     if not coordinates:
#         return {
#             "score": None, "label": "Unavailable",
#             "police_stations": 0, "hospitals": 0,
#             "police_facilities": [], "hospital_facilities": [],
#             "message": "No route coordinates were provided."
#         }

#     # GeoJSON coordinates are [longitude, latitude]. Use the route's actual
#     # bounds, padded by about 700 m, then filter returned facilities by distance.
#     valid = [(float(c[0]), float(c[1])) for c in coordinates if len(c) >= 2]
#     if not valid:
#         return {
#             "score": None, "label": "Unavailable",
#             "police_stations": 0, "hospitals": 0,
#             "police_facilities": [], "hospital_facilities": [],
#             "message": "Route coordinates could not be processed."
#         }

#     lons = [p[0] for p in valid]
#     lats = [p[1] for p in valid]
#     mean_lat = sum(lats) / len(lats)
#     lat_pad = 0.008
#     lon_pad = 0.008 / max(0.2, math.cos(math.radians(mean_lat)))
#     south, north = min(lats) - lat_pad, max(lats) + lat_pad
#     west, east = min(lons) - lon_pad, max(lons) + lon_pad

#     # A single nwr query is smaller than six separate node/way/relation queries.
#     # Overpass public servers can be temporarily busy, so try several instances.
#     query = f"""
#     [out:json][timeout:60];
#     nwr["amenity"~"^(police|hospital)$"]({south},{west},{north},{east});
#     out center tags;
#     """

#     endpoints = [
#         "https://overpass-api.de/api/interpreter",
#         "https://overpass.kumi.systems/api/interpreter",
#         "https://overpass.private.coffee/api/interpreter"
#     ]
#     data = None
#     last_error = None

#     for endpoint in endpoints:
#         try:
#             req = Request(
#                 endpoint,
#                 data=urlencode({"data": query}).encode("utf-8"),
#                 headers={
#                     "User-Agent": "SafeRouteStudentProject/1.0 (educational demo)",
#                     "Content-Type": "application/x-www-form-urlencoded"
#                 },
#                 method="POST"
#             )
#             with urlopen(req, timeout=70) as response:
#                 candidate = json.loads(response.read().decode("utf-8"))
#             if candidate.get("remark"):
#                 raise RuntimeError(candidate["remark"])
#             data = candidate
#             break
#         except Exception as error:
#             last_error = error

#     if data is None:
#         raise URLError(f"All OpenStreetMap Overpass servers failed: {last_error}")

#     # Approximate point-to-segment distance in metres using a local projection.
#     def point_segment_distance_m(lon, lat, a, b):
#         ref_lat = math.radians(lat)
#         scale_x = 111320 * math.cos(ref_lat)
#         scale_y = 110540
#         px, py = (lon - lon) * scale_x, (lat - lat) * scale_y
#         ax, ay = (a[0] - lon) * scale_x, (a[1] - lat) * scale_y
#         bx, by = (b[0] - lon) * scale_x, (b[1] - lat) * scale_y
#         dx, dy = bx - ax, by - ay
#         denom = dx * dx + dy * dy
#         t = 0 if denom == 0 else max(0, min(1, -(ax * dx + ay * dy) / denom))
#         return math.hypot(ax + t * dx, ay + t * dy)

#     def route_distance(lon, lat):
#         """Return the minimum approximate distance in metres to the route."""
#         best = float("inf")
#         for a, b in zip(valid, valid[1:]):
#             # Cheap geographic bounding-box rejection before projection.
#             min_lat = min(a[1], b[1]) - 0.006
#             max_lat = max(a[1], b[1]) + 0.006
#             lat_pad_local = 0.006 / max(0.2, math.cos(math.radians(lat)))
#             if not (min_lat <= lat <= max_lat and
#                     min(a[0], b[0]) - lat_pad_local <= lon <= max(a[0], b[0]) + lat_pad_local):
#                 continue
#             best = min(best, point_segment_distance_m(lon, lat, a, b))
#             if best <= 1:
#                 break
#         return best

#     police_by_id, hospitals_by_id = {}, {}
#     for element in data.get("elements", []):
#         tags = element.get("tags", {})
#         element_id = element.get("id")
#         if element_id is None:
#             continue
#         # Overpass returns node lat/lon and way/relation center lat/lon.
#         lat = element.get("lat", (element.get("center") or {}).get("lat"))
#         lon = element.get("lon", (element.get("center") or {}).get("lon"))
#         if lat is None or lon is None:
#             continue
#         lat, lon = float(lat), float(lon)
#         distance = route_distance(lon, lat)
#         if distance > 500:
#             continue

#         kind = tags.get("amenity")
#         if kind not in ("police", "hospital"):
#             continue
#         unique_id = (element.get("type", "element"), element_id)
#         facility = {
#             "id": f"{unique_id[0]}-{element_id}",
#             "name": tags.get("name") or ("Unnamed police station" if kind == "police" else "Unnamed hospital"),
#             "lat": lat,
#             "lon": lon,
#             "distance_m": round(distance),
#             "address": ", ".join(filter(None, [
#                 tags.get("addr:street"), tags.get("addr:suburb"), tags.get("addr:city")
#             ]))
#         }
#         target = police_by_id if kind == "police" else hospitals_by_id
#         target[unique_id] = facility

#     police_facilities = sorted(police_by_id.values(), key=lambda x: x["distance_m"])
#     hospital_facilities = sorted(hospitals_by_id.values(), key=lambda x: x["distance_m"])
#     police, hospitals = len(police_facilities), len(hospital_facilities)

#     # Support index: 40 base points plus up to 30 points for each category.
#     # Counts are capped so a dense city does not automatically imply perfect safety.
#     score = min(100, 40 + min(police, 6) * 5 + min(hospitals, 6) * 5)
#     if score >= 75:
#         label = "Higher mapped support"
#     elif score >= 55:
#         label = "Moderate mapped support"
#     else:
#         label = "Lower mapped support"

#     return {
#         "score": score,
#         "label": label,
#         "police_stations": police,
#         "hospitals": hospitals,
#         "police_facilities": police_facilities,
#         "hospital_facilities": hospital_facilities,
#         "corridor_m": 500,
#         "message": (
#             "Counts mapped within 500 m of the route. The index is a prototype "
#             "based on mapped support facilities; it does not measure crime rates "
#             "or guarantee safety."
#         )
#     }


# @app.route("/")
# def home():
#     return render_template("index.html")


# @app.route("/api/search")
# def api_search():
#     query = request.args.get("q", "").strip()

#     if len(query) < 3:
#         return jsonify({
#             "error": "Enter at least three characters."
#         }), 400

#     try:
#         return jsonify({
#             "results": search_places(query)
#         })

#     except (HTTPError, URLError, TimeoutError, OSError):
#         return jsonify({
#             "error": "Place search is temporarily unavailable. Try again."
#         }), 502

#     except (ValueError, KeyError, TypeError):
#         app.logger.exception("Place search failed")
#         return jsonify({
#             "error": "Could not process place-search results."
#         }), 502


# @app.route("/api/route")
# def get_route():
#     start = request.args.get("start", "").strip()
#     destination = request.args.get("destination", "").strip()

#     if not start or not destination:
#         return jsonify({
#             "error": "Enter both a starting location and destination."
#         }), 400

#     try:
#         # Use coordinates from selected search suggestions when available.
#         start_lat = request.args.get("start_lat", type=float)
#         start_lon = request.args.get("start_lon", type=float)
#         dest_lat = request.args.get("dest_lat", type=float)
#         dest_lon = request.args.get("dest_lon", type=float)

#         values = [start_lat, start_lon, dest_lat, dest_lon]
#         coordinates_provided = all(v is not None for v in values)

#         if coordinates_provided:
#             if not (
#                 -90 <= start_lat <= 90
#                 and -180 <= start_lon <= 180
#                 and -90 <= dest_lat <= 90
#                 and -180 <= dest_lon <= 180
#             ):
#                 return jsonify({
#                     "error": "Invalid location coordinates."
#                 }), 400

#             origin = {
#                 "name": start,
#                 "lat": start_lat,
#                 "lon": start_lon
#             }

#             target = {
#                 "name": destination,
#                 "lat": dest_lat,
#                 "lon": dest_lon
#             }

#         else:
#             origin_results = search_places(start)
#             target_results = search_places(destination)

#             if not origin_results:
#                 return jsonify({
#                     "error": "Starting location not found."
#                 }), 404

#             if not target_results:
#                 return jsonify({
#                     "error": "Destination not found."
#                 }), 404

#             origin = origin_results[0]
#             target = target_results[0]

#         # OSRM requires longitude,latitude pairs.
#         coordinates = (
#             f'{origin["lon"]},{origin["lat"]};'
#             f'{target["lon"]},{target["lat"]}'
#         )

#         params = urlencode({
#             "overview": "full",
#             "geometries": "geojson",
#             "alternatives": "true"
#         })

#         url = (
#             "https://router.project-osrm.org/route/v1/driving/"
#             + coordinates + "?" + params
#         )

#         req = Request(
#             url,
#             headers={
#                 "User-Agent": "SafeRouteStudentProject/1.0"
#             }
#         )

#         with urlopen(req, timeout=25) as response:
#             route_data = json.loads(response.read().decode("utf-8"))

#         if route_data.get("code") != "Ok" or not route_data.get("routes"):
#             return jsonify({
#                 "error": "No driving route found between these places."
#             }), 404

#         routes = []

#         for index, route in enumerate(route_data["routes"]):
#             safety = {
#                 "score": None,
#                 "label": "Unavailable",
#                 "police_stations": 0,
#                 "hospitals": 0,
#                 "message": "Safety information has not been retrieved."
#             }

#             # Retrieve safety data for each route independently.
            
#             try:
#                 safety = calculate_safety(route["geometry"], route.get("distance", 0))

#             except (HTTPError, URLError, TimeoutError, OSError):
#                 app.logger.exception(
#                     "Safety data unavailable for route %s", index + 1
#                 )
#                 safety = {
#                     "score": None,
#                     "label": "Unavailable",
#                     "police_stations": 0,
#                     "hospitals": 0,
#                     "police_facilities": [],
#                     "hospital_facilities": [],
#                     "message": "OpenStreetMap facility service could not be reached. Please retry in a minute."
#                 }

#             except (ValueError, KeyError, TypeError):
#                 app.logger.exception(
#                     "Safety calculation failed for route %s", index + 1
#                 )
#                 safety = {
#                     "score": None,
#                     "label": "Unavailable",
#                     "police_stations": 0,
#                     "hospitals": 0,
#                     "police_facilities": [],
#                     "hospital_facilities": [],
#                     "message": "Facility data was returned in an unexpected format. Please retry."
#                 }


#             routes.append({
#                 "distance_km": round(route["distance"] / 1000, 2),
#                 "duration_min": round(route["duration"] / 60),
#                 "geometry": route["geometry"],
#                 "safety": safety
#             })

#         return jsonify({
#             "origin": origin,
#             "destination": target,
#             "routes": routes
#         })

#     except HTTPError as error:
#         app.logger.warning("Map service returned HTTP %s", error.code)
#         return jsonify({
#             "error": "The routing service is temporarily unavailable."
#         }), 502

#     except (URLError, TimeoutError, OSError):
#         return jsonify({
#             "error": "Could not connect to a map service. Check your internet."
#         }), 502

#     except (ValueError, KeyError, TypeError):
#         app.logger.exception("Route calculation failed")
#         return jsonify({
#             "error": "Could not process the route. Please try again."
#         }), 502


# if __name__ == "__main__":
#     app.run(debug=True)

from flask import Flask, render_template, request, jsonify
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from urllib.parse import urlencode
import json
import time
import random
import math

app = Flask(__name__)

# Cache location search results
place_cache = {}
last_search_time = 0


# --------------------------------------------------
# LOCATION SEARCH
# --------------------------------------------------

def search_places(query):

    global last_search_time

    query = query.strip()

    if not query:
        return []

    if query in place_cache:
        return place_cache[query]

    # Nominatim rate limit
    elapsed = time.time() - last_search_time

    if elapsed < 1.1:
        time.sleep(1.1 - elapsed)

    params = urlencode({
        "q": query,
        "format": "json",
        "limit": 5
    })

    url = f"https://nominatim.openstreetmap.org/search?{params}"

    req = Request(
        url,
        headers={
            "User-Agent": "SafeRoute/1.0"
        }
    )

    with urlopen(req, timeout=15) as response:
        data = json.loads(response.read().decode())

    last_search_time = time.time()

    results = []

    for place in data:

        results.append({
            "name": place.get("display_name", ""),
            "lat": float(place["lat"]),
            "lon": float(place["lon"])
        })

    place_cache[query] = results

    return results


# --------------------------------------------------
# DISTANCE BETWEEN TWO COORDINATES
# --------------------------------------------------

def haversine(lat1, lon1, lat2, lon2):

    R = 6371000

    lat1 = math.radians(lat1)
    lon1 = math.radians(lon1)

    lat2 = math.radians(lat2)
    lon2 = math.radians(lon2)

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2)
        * math.sin(dlon / 2) ** 2
    )

    return 2 * R * math.asin(math.sqrt(a))


# --------------------------------------------------
# DISTANCE FROM A POINT TO A ROUTE
# --------------------------------------------------

def distance_to_route(lat, lon, coordinates):

    minimum_distance = float("inf")

    for i in range(len(coordinates) - 1):

        lon1, lat1 = coordinates[i]
        lon2, lat2 = coordinates[i + 1]

        # Approximate local coordinate conversion
        scale_x = 111320 * math.cos(math.radians(lat))
        scale_y = 111320

        x1 = (lon1 - lon) * scale_x
        y1 = (lat1 - lat) * scale_y

        x2 = (lon2 - lon) * scale_x
        y2 = (lat2 - lat) * scale_y

        dx = x2 - x1
        dy = y2 - y1

        if dx == 0 and dy == 0:
            distance = math.sqrt(x1 ** 2 + y1 ** 2)

        else:

            t = -(x1 * dx + y1 * dy) / (dx * dx + dy * dy)

            t = max(0, min(1, t))

            closest_x = x1 + t * dx
            closest_y = y1 + t * dy

            distance = math.sqrt(
                closest_x ** 2 + closest_y ** 2
            )

        minimum_distance = min(
            minimum_distance,
            distance
        )

    return minimum_distance


# --------------------------------------------------
# REAL SAFETY CALCULATION USING OPENSTREETMAP
# --------------------------------------------------

def calculate_safety(route_geometry, distance_m=0):

    coordinates = route_geometry.get("coordinates", [])

    if not coordinates:
        raise ValueError("Route geometry is empty")

    lats = [point[1] for point in coordinates]
    lons = [point[0] for point in coordinates]

    south = min(lats) - 0.008
    north = max(lats) + 0.008
    west = min(lons) - 0.008
    east = max(lons) + 0.008

    query = f"""
    [out:json][timeout:60];
    nwr["amenity"~"^(police|hospital)$"]
    ({south},{west},{north},{east});
    out center tags;
    """

    endpoints = [
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
        "https://overpass.private.coffee/api/interpreter"
    ]

    data = None

    for endpoint in endpoints:

        try:

            req = Request(
                endpoint,
                data=query.encode(),
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": "SafeRoute/1.0"
                },
                method="POST"
            )

            with urlopen(req, timeout=70) as response:
                data = json.loads(response.read().decode())

            break

        except Exception as e:

            app.logger.warning(
                "Overpass endpoint failed: %s",
                str(e)
            )

    if data is None:
        raise URLError("All Overpass servers failed")

    hospitals = []
    police_stations = []

    for element in data.get("elements", []):

        tags = element.get("tags", {})

        if "lat" in element and "lon" in element:

            lat = element["lat"]
            lon = element["lon"]

        elif "center" in element:

            lat = element["center"]["lat"]
            lon = element["center"]["lon"]

        else:
            continue

        distance = distance_to_route(
            lat,
            lon,
            coordinates
        )

        # Only facilities within 500 metres
        if distance > 500:
            continue

        name = tags.get("name", "Unnamed facility")

        facility = {
            "id": element.get("id"),
            "name": name,
            "lat": lat,
            "lon": lon,
            "distance": round(distance),
            "address": tags.get("addr:full", "")
        }

        if tags.get("amenity") == "hospital":
            hospitals.append(facility)

        elif tags.get("amenity") == "police":
            police_stations.append(facility)

    # Safety score
    score = min(
        100,
        40
        + min(len(police_stations), 6) * 5
        + min(len(hospitals), 6) * 5
    )

    if score >= 75:
        label = "Higher Safety"

    elif score >= 55:
        label = "Moderate Safety"

    else:
        label = "Lower Safety"

    return {
        "score": score,
        "label": label,
        "hospital_count": len(hospitals),
        "police_count": len(police_stations),
        "hospitals": hospitals,
        "police_stations": police_stations,
        "demo_mode": False,
        "message": "Safety data retrieved from OpenStreetMap."
    }


# --------------------------------------------------
# DEMO FALLBACK IF OPENSTREETMAP FAILS
# --------------------------------------------------

def generate_demo_safety(start, destination):

    hospitals = [
        "Felix Hospital",
        "Apollo Hospital",
        "Max Super Speciality Hospital",
        "Fortis Hospital"
    ]

    police_stations = [
        "Cyber Police Station NCR"
    ]

    # Extract approximate area from destination
    parts = [
        p.strip()
        for p in destination.split(",")
        if p.strip()
    ]

    if len(parts) >= 3:
        area = ", ".join(parts[-3:])
    else:
        area = destination

    hospital_data = []

    for i, name in enumerate(hospitals):

        hospital_data.append({
            "id": f"demo_hospital_{i}",
            "name": name,
            "address": f"Demo location near {area} (unverified)",
            "demo": True
        })

    police_data = []

    for i, name in enumerate(police_stations):

        police_data.append({
            "id": f"demo_police_{i}",
            "name": name,
            "address": f"Demo location near {area} (unverified)",
            "demo": True
        })

    score = random.randint(60, 100)

    return {
        "score": score,
        "label": "Demo Score (Simulated)",
        "hospital_count": len(hospital_data),
        "police_count": len(police_data),
        "hospitals": hospital_data,
        "police_stations": police_data,
        "demo_mode": True,
        "message": (
            "Simulated safety data. Facility names and locations "
            "are not verified nearby results."
        )
    }


# --------------------------------------------------
# HOME PAGE
# --------------------------------------------------

@app.route("/")
def home():

    return render_template("index.html")


# --------------------------------------------------
# LOCATION SEARCH API
# --------------------------------------------------

@app.route("/api/search", methods=["GET"])
def api_search():

    query = request.args.get("q", "").strip()

    if not query:
        return jsonify([])

    try:

        results = search_places(query)

        return jsonify(results)

    except Exception as e:

        app.logger.exception("Location search failed")

        return jsonify({
            "error": "Location search failed",
            "details": str(e)
        }), 500


# --------------------------------------------------
# ROUTE CALCULATION API
# --------------------------------------------------

@app.route("/api/route", methods=["POST"])
def get_route():

    data = request.get_json(silent=True) or {}

    start = data.get("start", "").strip()
    destination = data.get("destination", "").strip()

    if not start or not destination:

        return jsonify({
            "error": "Start and destination are required"
        }), 400

    try:

        start_lat = data.get("start_lat")
        start_lon = data.get("start_lon")

        dest_lat = data.get("dest_lat")
        dest_lon = data.get("dest_lon")

        # Geocode start if coordinates are missing
        if start_lat is None or start_lon is None:

            start_results = search_places(start)

            if not start_results:
                return jsonify({
                    "error": "Starting location not found"
                }), 404

            start_lat = start_results[0]["lat"]
            start_lon = start_results[0]["lon"]

        # Geocode destination if coordinates are missing
        if dest_lat is None or dest_lon is None:

            dest_results = search_places(destination)

            if not dest_results:
                return jsonify({
                    "error": "Destination not found"
                }), 404

            dest_lat = dest_results[0]["lat"]
            dest_lon = dest_results[0]["lon"]

        start_lat = float(start_lat)
        start_lon = float(start_lon)

        dest_lat = float(dest_lat)
        dest_lon = float(dest_lon)

        # OSRM routing
        coordinates = (
            f"{start_lon},{start_lat};"
            f"{dest_lon},{dest_lat}"
        )

        url = (
            "https://router.project-osrm.org/route/v1/driving/"
            f"{coordinates}"
            "?overview=full&geometries=geojson&alternatives=true"
        )

        req = Request(
            url,
            headers={
                "User-Agent": "SafeRoute/1.0"
            }
        )

        with urlopen(req, timeout=30) as response:
            route_data = json.loads(response.read().decode())

        if route_data.get("code") != "Ok":

            return jsonify({
                "error": "Could not calculate routes"
            }), 400

        routes = []

        for index, route in enumerate(
            route_data.get("routes", [])
        ):

            try:

                safety = calculate_safety(
                    route["geometry"],
                    route.get("distance", 0)
                )

                safety["demo_mode"] = False

            except Exception:

                app.logger.exception(
                    "Safety API failed for route %s. "
                    "Using demo data.",
                    index + 1
                )

                safety = generate_demo_safety(
                    start,
                    destination
                )

            routes.append({
                "route_number": index + 1,
                "distance": route.get("distance", 0),
                "duration": route.get("duration", 0),
                "geometry": route["geometry"],
                "safety": safety
            })

        return jsonify({
            "origin": {
                "name": start,
                "lat": start_lat,
                "lon": start_lon
            },
            "destination": {
                "name": destination,
                "lat": dest_lat,
                "lon": dest_lon
            },
            "routes": routes
        })

    except Exception as e:

        app.logger.exception("Route calculation failed")

        return jsonify({
            "error": "Route calculation failed",
            "details": str(e)
        }), 500


# --------------------------------------------------
# RUN APPLICATION
# --------------------------------------------------

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )
