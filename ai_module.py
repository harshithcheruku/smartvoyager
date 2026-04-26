import math
from datetime import datetime

class AIModule:
    @staticmethod
    def haversine(lat1, lon1, lat2, lon2):
        R = 6371000  # Earth radius in meters
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)

        a = math.sin(delta_phi / 2.0) ** 2 + \
            math.cos(phi1) * math.cos(phi2) * \
            math.sin(delta_lambda / 2.0) ** 2
        
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        return R * c

    @staticmethod
    def get_direction(lat1, lon1, lat2, lon2):
        dLon = math.radians(lon2 - lon1)
        lat1 = math.radians(lat1)
        lat2 = math.radians(lat2)
        y = math.sin(dLon) * math.cos(lat2)
        x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dLon)
        bearing = math.atan2(y, x)
        bearing = math.degrees(bearing)
        bearing = (bearing + 360) % 360
        
        dirs = ["North", "North-East", "East", "South-East", "South", "South-West", "West", "North-West"]
        ix = int(round(bearing / 45.0)) % 8
        return dirs[ix]

    @staticmethod
    def calculate_zone_score(user_lat, user_lon, geozones):
        if not geozones:
            return 0.0, "No geo-zones defined.", False, None, None

        highest_score = 0.0
        zone_reason = "Outside all known geo-zones."
        is_restricted = False
        zone_name = None
        zone_type = None
        
        for zone in geozones:
            dist = AIModule.haversine(user_lat, user_lon, zone.latitude, zone.longitude)
            if dist <= zone.radius:
                z_type = getattr(zone, 'type', 'RISK')
                
                # Highest priority: Restricted zone
                if z_type == "RESTRICTED":
                    highest_score = 3.0
                    zone_reason = f"Restricted Zone: '{zone.name}'"
                    is_restricted = True
                    zone_name = zone.name
                    zone_type = "RESTRICTED"
                    break # Hard override, exit loop immediately
                
                # Standard risk zone logic
                if z_type == "SAFE":
                    if highest_score < 0.5:
                        highest_score = 0.5
                        zone_reason = f"Inside SAFE zone: '{zone.name}'"
                        zone_name = zone.name
                        zone_type = "SAFE"
                elif zone.risk_level == "LOW" and highest_score < 1.0:
                    highest_score = 1.0
                    zone_reason = f"Inside LOW risk geo-zone: '{zone.name}'"
                    zone_name = zone.name
                    zone_type = z_type
                elif zone.risk_level == "MEDIUM" and highest_score < 2.0:
                    highest_score = 2.0
                    zone_reason = f"Inside MEDIUM risk geo-zone: '{zone.name}'"
                    zone_name = zone.name
                    zone_type = z_type
                elif zone.risk_level == "HIGH" and highest_score < 3.0:
                    highest_score = 3.0
                    zone_reason = f"High Risk Zone: '{zone.name}'"
                    zone_name = zone.name
                    zone_type = z_type
                    
        return highest_score, zone_reason, is_restricted, zone_name, zone_type

    @staticmethod
    def calculate_incident_score(user_lat, user_lon, active_incidents):
        if not active_incidents:
            return 0.0, "No incidents reported nearby."

        score = 0.0
        incident_count = 0
        
        for incident in active_incidents:
            if incident.status != 'active':
                continue

            dist = AIModule.haversine(user_lat, user_lon, incident.latitude, incident.longitude)
            if dist <= 500:
                score += round((500 - dist) / 500, 3)
                incident_count += 1
                
        if incident_count > 0:
            incident_reason = f"{incident_count} active incident(s) detected within 500m."
        else:
            incident_reason = "No active incidents within 500m."
            
        score = min(score, 3.0)
        return score, incident_reason

    @staticmethod
    def generate_safety_suggestions(risk_level, place_type, time_hour, incident_count, response_time):
        suggestions = []
        is_night = time_hour >= 20 or time_hour < 6

        if risk_level == "LOW":
            return [] # No suggestions for low risk

        # MEDIUM RISK SUGGESTIONS (Preventive)
        if risk_level == "MEDIUM":
            suggestions.append("Stay alert and keep emergency contacts ready.")
            if is_night:
                if place_type in ["market", "tourist_spot"]:
                    suggestions.append("Stay near well-lit shops and avoid dark side streets.")
                elif place_type == "forest":
                    suggestions.append("Avoid venturing deep; stay on marked paths.")
                else:
                    suggestions.append("Avoid isolated areas at this hour.")
            else:
                if place_type == "transport":
                    suggestions.append("Keep belongings secure in transit hubs.")
                elif incident_count > 0:
                    suggestions.append("Recent incidents reported nearby. Stay cautious.")
            
            if response_time > 20:
                suggestions.append("Note: Emergency response times in this area are longer than usual.")

        # HIGH RISK SUGGESTIONS (Urgent / Action-based)
        elif risk_level == "HIGH":
            suggestions.append("URGENT: Leave the area immediately or move to a crowded public place.")
            if is_night:
                suggestions.append("Move to well-lit areas with security personnel or crowds.")
            
            if place_type == "tourist_spot":
                suggestions.append("Move towards the main entrance or a security checkpoint.")
            elif place_type == "transport":
                suggestions.append("Seek station security or transport staff immediately.")
            
            if incident_count > 0:
                suggestions.append("Multiple incidents detected in this vicinity. Exercise extreme caution.")
            
            if response_time <= 15:
                suggestions.append("Emergency services are on standby and can respond quickly if needed.")
            else:
                suggestions.append("WARNING: Emergency response may be delayed. Prioritize your own immediate safety.")
                
        return suggestions

    @staticmethod
    def evaluate_risk(user_lat, user_lon, geozones, active_incidents):
        # 1. Geo-Zone Detection
        zone_score, zone_reason, is_restricted, zone_name, zone_type = AIModule.calculate_zone_score(user_lat, user_lon, geozones)
        
        place_type = "general"
        avg_response_time = 15
        
        # Get zone details for the highest risk zone affecting the user
        for zone in geozones:
            if zone.name == zone_name:
                place_type = getattr(zone, 'place_type', 'general')
                avg_response_time = getattr(zone, 'avg_response_time', 15)
                break

        # 2. Incident Scoring
        incident_score, incident_reason = AIModule.calculate_incident_score(user_lat, user_lon, active_incidents)
        incident_count_actual = sum(1 for inc in active_incidents if inc.status == 'active' and AIModule.haversine(user_lat, user_lon, inc.latitude, inc.longitude) <= 500)
        
        # 3. Final Score Calculation (Pre-time-modifier)
        final_score = zone_score + incident_score
        
        # Moderate weighting based on place type and response time
        if place_type in ["nightlife", "isolated"]:
            final_score += 0.5
        elif place_type in ["forest"]:
            final_score += 0.2
            
        if avg_response_time > 20:
            final_score += 0.3 # Penalize slow response areas
        
        # 4. Time-Based Modifier
        current_hour = datetime.now().hour
        time_reason = "Standard time."
        if current_hour >= 21 or current_hour < 5:
            final_score *= 1.2
            time_reason = "Night-time (higher risk period, x1.2 applied)."

        # 5. Risk Classification (Strict overrides for restricted zones)
        if is_restricted:
            risk_level = "HIGH"
        elif final_score < 1.5:
            risk_level = "LOW"
        elif final_score < 3.5:
            risk_level = "MEDIUM"
        else:
            risk_level = "HIGH"

        reason = f"Zone: {zone_reason}|Incidents: {incident_reason}|Time: {time_reason}"

        suggestions = AIModule.generate_safety_suggestions(risk_level, place_type, current_hour, incident_count_actual, avg_response_time)
        
        # Auto SOS logic
        should_auto_sos = False
        if final_score > 5.0 and (is_restricted or incident_count_actual >= 2):
            should_auto_sos = True
            
        # Alert Type mapping
        alert_type = "none"
        if risk_level == "MEDIUM":
            alert_type = "warning"
        elif risk_level == "HIGH":
            alert_type = "critical"
            
        # SafeRoute AI Guidance
        safe_destination = None
        safe_distance_meters = None
        safe_direction = None
        eta_minutes = None
        escape_advice = None
        
        if risk_level in ["MEDIUM", "HIGH"]:
            nearest_safe_zone = None
            min_dist = float('inf')
            for zone in geozones:
                if getattr(zone, 'type', 'RISK') == 'SAFE':
                    dist = AIModule.haversine(user_lat, user_lon, zone.latitude, zone.longitude)
                    if dist < min_dist:
                        min_dist = dist
                        nearest_safe_zone = zone
                        
            if nearest_safe_zone:
                safe_destination = nearest_safe_zone.name
                safe_distance_meters = int(min_dist)
                safe_direction = AIModule.get_direction(user_lat, user_lon, nearest_safe_zone.latitude, nearest_safe_zone.longitude)
                eta_minutes = math.ceil(min_dist / 1.38 / 60) # 1.38 m/s = 5 km/h
                escape_advice = "Move immediately toward nearest safe zone and remain in visible public area."
            else:
                escape_advice = "Move toward nearest crowded road, shop, security point, or authority area."

        return {
            "risk_level": (risk_level or "LOW"),
            "score": float(round(final_score, 2) if final_score is not None else 0),
            "reason": (reason or ""),
            "is_restricted": bool(is_restricted),
            "zone_name": zone_name if zone_name else None,
            "zone_type": zone_type if zone_type else None,
            "suggestions": suggestions if isinstance(suggestions, list) else [],
            "should_auto_sos": bool(should_auto_sos),
            "alert_type": (alert_type or "none"),
            "safe_destination": safe_destination,
            "safe_distance_meters": safe_distance_meters,
            "safe_direction": safe_direction,
            "eta_minutes": eta_minutes,
            "escape_advice": escape_advice
        }
