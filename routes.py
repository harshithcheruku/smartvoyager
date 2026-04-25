from flask import Blueprint, request, jsonify, abort
from werkzeug.exceptions import HTTPException
from models import User, Location, GeoZone, Incident
from db import db
from ai_module import AIModule
import jwt
import os
from functools import wraps
from datetime import datetime, timedelta

# Helper coordinates validator
def validate_coordinates(lat, lon):
    try:
        lat, lon = float(lat), float(lon)
        if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
            return False, "Coordinates out of bounds (Lat: -90 to 90, Lon: -180 to 180)", None, None
        return True, "", lat, lon
    except (ValueError, TypeError):
        return False, "Invalid coordinate format", None, None

def get_secret_key():
    from flask import current_app
    return current_app.config['SECRET_KEY']

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        try:
            token = None
            auth_header = request.headers.get('Authorization')
            if auth_header:
                parts = auth_header.split()
                if len(parts) == 2 and parts[0] == 'Bearer':
                    token = parts[1]
                    
            if not token:
                return jsonify({"status": "error", "error": "Token is missing", "data": {}}), 401

            data = jwt.decode(token, get_secret_key(), algorithms=["HS256"])
            current_user = db.session.get(User, data.get('user_id'))
            if not current_user:
                return jsonify({"status": "error", "error": "User not found", "data": {}}), 401
                
        except jwt.ExpiredSignatureError:
            return jsonify({"status": "error", "error": "Token has expired", "data": {}}), 401
        except Exception as e:
            return jsonify({"status": "error", "error": "Token is invalid or expired", "data": {}}), 401

        return f(current_user, *args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(current_user, *args, **kwargs):
        if current_user.role != 'admin':
            return jsonify({"status": "error", "error": "Admin privileges required", "data": {}}), 403
        return f(current_user, *args, **kwargs)
    return decorated


# Authentication Blueprint
auth_bp = Blueprint('auth_bp', __name__)

@auth_bp.route('/api/register', methods=['POST'])
def register():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "error": "No JSON body provided", "data": {}}), 400
            
        name = data.get('name')
        email = data.get('email')
        password = data.get('password')

        if not name or not email or not password:
            return jsonify({"status": "error", "error": "Missing fields", "data": {}}), 400

        if User.query.filter_by(email=email).first():
            return jsonify({"status": "error", "error": "Email already registered", "data": {}}), 400

        # Assign admin role only for specific email
        admin_email = os.environ.get('ADMIN_EMAIL', 'admin@smartvoyager.com')
        role = 'admin' if email.lower() == admin_email.lower() else 'user'
        new_user = User(name=name, email=email, role=role)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()

        return jsonify({"status": "success", "data": {"message": "User registered successfully"}, "error": ""}), 201
    except HTTPException as e:
        return jsonify({"status": "error", "error": e.description, "data": {}}), e.code
    except Exception as e:
        return jsonify({"status": "error", "error": str(e), "data": {}}), 500

@auth_bp.route('/api/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "error": "No JSON body provided", "data": {}}), 400
            
        email = data.get('email')
        password = data.get('password')

        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(password):
            return jsonify({"status": "error", "error": "Invalid credentials", "data": {}}), 401

        # Generate JWT Token
        token = jwt.encode({
            'user_id': user.id,
            'role': user.role,
            'exp': datetime.utcnow() + timedelta(hours=24)
        }, get_secret_key(), algorithm="HS256")

        if isinstance(token, bytes):
            token = token.decode('utf-8')

        return jsonify({
            "status": "success", 
            "data": {
                "message": "Login successful", 
                "user_id": user.id, 
                "name": user.name,
                "role": user.role,
                "token": token
            },
            "error": ""
        }), 200
    except HTTPException as e:
        return jsonify({"status": "error", "error": e.description, "data": {}}), e.code
    except Exception as e:
        return jsonify({"status": "error", "error": str(e), "data": {}}), 500


# User Blueprint
user_bp = Blueprint('user_bp', __name__)

@user_bp.route('/api/location/update', methods=['POST'])
@token_required
def update_location(current_user):
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "error": "No JSON body provided", "data": {}}), 400
            
        lat = data.get('latitude')
        lon = data.get('longitude')

        if lat is None or lon is None:
            return jsonify({"status": "error", "error": "Missing latitude or longitude", "data": {}}), 400

        is_valid, msg, lat, lon = validate_coordinates(lat, lon)
        if not is_valid:
            return jsonify({"status": "error", "error": msg, "data": {}}), 400

        location = Location(user_id=current_user.id, latitude=lat, longitude=lon)
        db.session.add(location)
        db.session.commit()

        return jsonify({"status": "success", "data": {"message": "Location updated"}, "error": ""}), 200
    except HTTPException as e:
        return jsonify({"status": "error", "error": e.description, "data": {}}), e.code
    except Exception as e:
        return jsonify({"status": "error", "error": str(e), "data": {}}), 500

@user_bp.route('/api/risk', methods=['GET'])
@token_required
def get_risk(current_user):
    try:
        lat_str = request.args.get('latitude')
        lon_str = request.args.get('longitude')

        if lat_str is None or lon_str is None:
            return jsonify({"status": "error", "error": "Missing latitude or longitude params", "data": {}}), 400

        try:
            lat = float(lat_str)
            lon = float(lon_str)
        except (ValueError, TypeError):
            return jsonify({"status": "error", "error": "Invalid latitude or longitude format. Must be numbers.", "data": {}}), 400

        is_valid, msg, lat, lon = validate_coordinates(lat, lon)
        if not is_valid:
            return jsonify({"status": "error", "error": msg, "data": {}}), 400

        geozones = GeoZone.query.all()
        active_incidents = Incident.query.filter_by(status='active').all()

        risk_data = AIModule.evaluate_risk(lat, lon, geozones, active_incidents)

        return jsonify({"status": "success", "data": risk_data, "error": ""}), 200
        
    except HTTPException as e:
        return jsonify({"status": "error", "error": e.description, "data": {}}), e.code
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "error": f"Internal Server Error: {str(e)}", "data": {}}), 500

@user_bp.route('/api/sos', methods=['POST'])
@token_required
def sos(current_user):
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "error": "No JSON body provided", "data": {}}), 400
            
        lat = data.get('latitude')
        lon = data.get('longitude')
        inc_type = data.get('type', 'emergency')

        if lat is None or lon is None:
            return jsonify({"status": "error", "error": "Missing required fields", "data": {}}), 400

        is_valid, msg, lat, lon = validate_coordinates(lat, lon)
        if not is_valid:
            return jsonify({"status": "error", "error": msg, "data": {}}), 400

        incident = Incident(user_id=current_user.id, latitude=lat, longitude=lon, type=inc_type, status='active')
        db.session.add(incident)
        db.session.commit()

        return jsonify({"status": "success", "data": {"message": "SOS alert created", "incident_id": incident.id}, "error": ""}), 201
    except HTTPException as e:
        return jsonify({"status": "error", "error": e.description, "data": {}}), e.code
    except Exception as e:
        return jsonify({"status": "error", "error": str(e), "data": {}}), 500

@user_bp.route('/api/incidents/user', methods=['GET'])
@token_required
def get_user_incidents(current_user):
    try:
        incidents = Incident.query.filter_by(user_id=current_user.id).order_by(Incident.id.desc()).all()
        data = [
            {"id": i.id, "type": i.type, "status": i.status, "timestamp": i.timestamp.isoformat() if i.timestamp else None}
            for i in incidents
        ]
        return jsonify({"status": "success", "data": {"incidents": data}, "error": ""}), 200
    except HTTPException as e:
        return jsonify({"status": "error", "error": e.description, "data": {}}), e.code
    except Exception as e:
        return jsonify({"status": "error", "error": str(e), "data": {}}), 500

@user_bp.route('/api/zones/public', methods=['GET'])
@token_required
def get_public_zones(current_user):
    try:
        zones = GeoZone.query.all()
        data = [{"id": z.id, "name": z.name, "latitude": z.latitude, "longitude": z.longitude, "radius": z.radius, "risk_level": z.risk_level, "type": getattr(z, 'type', 'RISK')} for z in zones]
        return jsonify({"status": "success", "data": {"zones": data}, "error": ""}), 200
    except HTTPException as e:
        return jsonify({"status": "error", "error": e.description, "data": {}}), e.code
    except Exception as e:
        return jsonify({"status": "error", "error": str(e), "data": {}}), 500


# Authority Blueprint
authority_bp = Blueprint('authority_bp', __name__)

@authority_bp.route('/api/incidents', methods=['GET'])
@token_required
@admin_required
def get_incidents(current_user):
    try:
        status_filter = request.args.get('status')
        query = Incident.query
        
        if status_filter:
            query = query.filter_by(status=status_filter)
            
        incidents = query.all()
        
        data = [
            {"id": i.id, "user_id": i.user_id, "latitude": i.latitude, "longitude": i.longitude, "type": i.type, "status": i.status, "timestamp": i.timestamp.isoformat() if i.timestamp else None}
            for i in incidents
        ]
        return jsonify({"status": "success", "data": {"incidents": data}, "error": ""}), 200
    except HTTPException as e:
        return jsonify({"status": "error", "error": e.description, "data": {}}), e.code
    except Exception as e:
        return jsonify({"status": "error", "error": str(e), "data": {}}), 500

@authority_bp.route('/api/incidents/<int:incident_id>', methods=['PUT'])
@token_required
@admin_required
def resolve_incident(current_user, incident_id):
    try:
        incident = Incident.query.get_or_404(incident_id, description="Incident not found")
        incident.status = 'resolved'
        db.session.commit()
        return jsonify({"status": "success", "data": {"message": "Incident resolved"}, "error": ""}), 200
    except HTTPException as e:
        return jsonify({"status": "error", "error": e.description, "data": {}}), e.code
    except Exception as e:
        return jsonify({"status": "error", "error": str(e), "data": {}}), 500

@authority_bp.route('/api/sos/heatmap', methods=['GET'])
@token_required
@admin_required
def get_sos_heatmap(current_user):
    try:
        incidents = Incident.query.filter_by(status='active').all()
        data = [
            {"latitude": i.latitude, "longitude": i.longitude, "intensity": 1.0}
            for i in incidents
        ]
        return jsonify({"status": "success", "data": data, "error": ""}), 200
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "error": str(e), "data": {}}), 500

@authority_bp.route('/api/geozones', methods=['POST', 'GET'])
@token_required
@admin_required
def manage_geozones(current_user):
    try:
        if request.method == 'POST':
            data = request.get_json()
            if not data:
                return jsonify({"status": "error", "error": "No JSON body provided", "data": {}}), 400
                
            name = data.get('name')
            lat = data.get('latitude')
            lon = data.get('longitude')
            radius = data.get('radius')
            risk_level = data.get('risk_level')
            zone_type = data.get('type', 'RISK')
            
            if not name or lat is None or lon is None or radius is None or not risk_level:
                return jsonify({"status": "error", "error": "Missing required fields for GeoZone", "data": {}}), 400
                
            is_valid, msg, lat, lon = validate_coordinates(lat, lon)
            if not is_valid:
                return jsonify({"status": "error", "error": msg, "data": {}}), 400
                
            try:
                radius = float(radius)
                if radius <= 0:
                    return jsonify({"status": "error", "error": "Radius must be strictly positive", "data": {}}), 400
            except ValueError:
                return jsonify({"status": "error", "error": "Invalid radius format", "data": {}}), 400
                
            if risk_level not in ["LOW", "MEDIUM", "HIGH"]:
                return jsonify({"status": "error", "error": "risk_level must be LOW, MEDIUM, or HIGH", "data": {}}), 400
                
            if zone_type not in ["RISK", "RESTRICTED", "SAFE"]:
                return jsonify({"status": "error", "error": "type must be RISK, RESTRICTED, or SAFE", "data": {}}), 400
                
            zone = GeoZone(
                name=name,
                latitude=lat,
                longitude=lon,
                radius=radius,
                risk_level=risk_level,
                type=zone_type
            )
            db.session.add(zone)
            db.session.commit()
            return jsonify({"status": "success", "data": {"message": "GeoZone added", "zone_id": zone.id}, "error": ""}), 201
        
        else: # GET
            zones = GeoZone.query.all()
            data = [{"id": z.id, "name": z.name, "latitude": z.latitude, "longitude": z.longitude, "radius": z.radius, "risk_level": z.risk_level, "type": getattr(z, 'type', 'RISK')} for z in zones]
            return jsonify({"status": "success", "data": {"geozones": data}, "error": ""}), 200
    except HTTPException as e:
        return jsonify({"status": "error", "error": e.description, "data": {}}), e.code
    except Exception as e:
        return jsonify({"status": "error", "error": str(e), "data": {}}), 500

@authority_bp.route('/api/geozones/<int:zone_id>', methods=['PUT', 'DELETE'])
@token_required
@admin_required
def modify_geozone(current_user, zone_id):
    try:
        zone = GeoZone.query.get_or_404(zone_id, description="Zone not found")
        
        if request.method == 'PUT':
            data = request.get_json()
            if not data:
                return jsonify({"status": "error", "error": "No JSON body provided", "data": {}}), 400
                
            name = data.get('name')
            lat = data.get('latitude')
            lon = data.get('longitude')
            radius = data.get('radius')
            risk_level = data.get('risk_level')
            zone_type = data.get('type')
            
            if name: zone.name = name
            if lat is not None:
                try: zone.latitude = float(lat)
                except ValueError: return jsonify({"status": "error", "error": "Invalid latitude", "data": {}}), 400
            if lon is not None:
                try: zone.longitude = float(lon)
                except ValueError: return jsonify({"status": "error", "error": "Invalid longitude", "data": {}}), 400
            if radius is not None:
                try: 
                    radius = float(radius)
                    if radius <= 0: return jsonify({"status": "error", "error": "Radius must be strictly positive", "data": {}}), 400
                    zone.radius = radius
                except ValueError: return jsonify({"status": "error", "error": "Invalid radius", "data": {}}), 400
            if risk_level:
                if risk_level not in ["LOW", "MEDIUM", "HIGH"]:
                    return jsonify({"status": "error", "error": "Invalid risk level", "data": {}}), 400
                zone.risk_level = risk_level
            if zone_type:
                if zone_type not in ["RISK", "RESTRICTED", "SAFE"]:
                    return jsonify({"status": "error", "error": "Invalid zone type", "data": {}}), 400
                zone.type = zone_type
                
            db.session.commit()
            return jsonify({"status": "success", "data": {"message": "GeoZone updated"}, "error": ""}), 200
            
        elif request.method == 'DELETE':
            db.session.delete(zone)
            db.session.commit()
            return jsonify({"status": "success", "data": {"message": "Zone deleted"}, "error": ""}), 200
            
    except HTTPException as e:
        return jsonify({"status": "error", "error": e.description, "data": {}}), e.code
    except Exception as e:
        return jsonify({"status": "error", "error": str(e), "data": {}}), 500
