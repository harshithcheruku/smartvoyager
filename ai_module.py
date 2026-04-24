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
    def evaluate_risk(user_lat, user_lon, geozones, active_incidents):
        # 1. Geo-Zone Detection
        zone_score, zone_reason, is_restricted, zone_name, zone_type = AIModule.calculate_zone_score(user_lat, user_lon, geozones)
        
        # 2. Incident Scoring
        incident_score, incident_reason = AIModule.calculate_incident_score(user_lat, user_lon, active_incidents)
        
        # 3. Final Score Calculation (Pre-time-modifier)
        final_score = zone_score + incident_score
        
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
        elif final_score < 3.0:
            risk_level = "MEDIUM"
        else:
            risk_level = "HIGH"

        reason = f"Zone: {zone_reason}|Incidents: {incident_reason}|Time: {time_reason}"

        return {
            "risk_level": risk_level,
            "score": round(final_score, 2),
            "reason": reason,
            "is_restricted": is_restricted,
            "zone_name": zone_name,
            "zone_type": zone_type
        }
