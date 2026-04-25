from flask import Blueprint, request, jsonify, abort
from werkzeug.exceptions import HTTPException
from models import User, Location, GeoZone, Incident
from db import db
from ai_module import AIModule
import jwt
import os
import traceback
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
                return jsonify({"status": "error", "error": "Token is missing"}), 401

            data = jwt.decode(token, get_secret_key(), algorithms=["HS256"])
            current_user = db.session.get(User, data.get('user_id'))
            if not current_user:
                return jsonify({"status": "error", "error": "User not found"}), 401
                
        except jwt.ExpiredSignatureError:
            return jsonify({"status": "error", "error": "Token has expired"}), 401
        except Exception as e:
            traceback.print_exc()
            return jsonify({"status": "error", "error": "Token is invalid or expired"}), 401

        return f(current_user, *args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(current_user, *args, **kwargs):
        if current_user.role != 'admin':
            return jsonify({"status": "error", "error": "Admin privileges required"}), 403
        return f(current_user, *args, **kwargs)
    return decorated


# Authentication Blueprint
auth_bp = Blueprint('auth_bp', __name__)

@auth_bp.route('/api/register', methods=['POST'])
def register():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "error": "No JSON body provided"}), 400
            
        name = data.get('name')
        email = data.get('email')
        password = data.get('password')

        if not name or not email or not password:
            return jsonify({"status": "error", "error": "Missing fields"}), 400

        if User.query.filter_by(email=email).first():
            return jsonify({"status": "error", "error": "Email already registered"}), 400

        # Assign admin role only for specific email
        admin_email = os.environ.get('ADMIN_EMAIL', 'admin@smartvoyager.com')
        role = 'admin' if email.lower() == admin_email.lower() else 'user'
        new_user = User(name=name, email=email, role=role)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()

        return jsonify({"status": "success", "data": {"message": "User registered successfully"}}), 201
    except HTTPException as e:
        return jsonify({"status": "error", "error": str(e.description)}), e.code
    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "error": str(e)}), 500

@auth_bp.route('/api/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "error": "No JSON body provided"}), 400
            
        email = data.get('email')
        password = data.get('password')

        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(password):
            return jsonify({"status": "error", "error": "Invalid credentials"}), 401

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
            }
        }), 200
    except HTTPException as e:
        return jsonify({"status": "error", "error": str(e.description)}), e.code
    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "error": str(e)}), 500


# User Blueprint
user_bp = Blueprint('user_bp', __name__)

@user_bp.route('/api/location/update', methods=['POST'])
@token_required
def update_location(current_user):
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "error": "No JSON body provided"}), 400
            
        lat = data.get('latitude')
        lon = data.get('longitude')

        if lat is None or lon is None:
            return jsonify({"status": "error", "error": "Missing latitude or longitude"}), 400

        is_valid, msg, lat, lon = validate_coordinates(lat, lon)
        if not is_valid:
            return jsonify({"status": "error", "error": msg}), 400

        location = Location(user_id=current_user.id, latitude=lat, longitude=lon)
        db.session.add(location)
        db.session.commit()

        return jsonify({"status": "success", "data": {"message": "Location updated"}}), 200
    except HTTPException as e:
        return jsonify({"status": "error", "error": str(e.description)}), e.code
    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "error": str(e)}), 500

@user_bp.route('/api/risk', methods=['GET'])
@token_required
def get_risk(current_user):
    try:
        lat_str = request.args.get('latitude')
        lon_str = request.args.get('longitude')

        if lat_str is None or lon_str is None:
            return jsonify({"status": "error", "error": "Missing latitude or longitude params"}), 400

        try:
            lat = float(lat_str)
            lon = float(lon_str)
        except (ValueError, TypeError):
            return jsonify({"status": "error", "error": "Invalid latitude or longitude format. Must be numbers."}), 400

        is_valid, msg, lat, lon = validate_coordinates(lat, lon)
        if not is_valid:
            return jsonify({"status": "error", "error": msg}), 400

        geozones = GeoZone.query.limit(100).all()
        active_incidents = Incident.query.filter_by(status='active').all()

        risk_data = AIModule.evaluate_risk(lat, lon, geozones, active_incidents)

        if risk_data.get("should_auto_sos"):
            five_mins_ago = datetime.utcnow() - timedelta(minutes=5)
            recent_auto_sos = Incident.query.filter_by(
                user_id=current_user.id, auto_triggered=True
            ).filter(Incident.timestamp >= five_mins_ago).first()
            
            if not recent_auto_sos:
                auto_inc = Incident(user_id=current_user.id, latitude=lat, longitude=lon, type='auto_emergency', status='active', auto_triggered=True)
                db.session.add(auto_inc)
                db.session.commit()

        return jsonify({"status": "success", "data": risk_data}), 200
        
    except HTTPException as e:
        return jsonify({"status": "error", "error": str(e.description)}), e.code
    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "error": f"Internal Server Error: {str(e)}"}), 500

@user_bp.route('/api/sos', methods=['POST'])
@token_required
def sos(current_user):
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "error": "No JSON body provided"}), 400
            
        lat = data.get('latitude')
        lon = data.get('longitude')
        inc_type = data.get('type', 'emergency')

        if lat is None or lon is None:
            return jsonify({"status": "error", "error": "Missing required fields"}), 400

        is_valid, msg, lat, lon = validate_coordinates(lat, lon)
        if not is_valid:
            return jsonify({"status": "error", "error": msg}), 400

        incident = Incident(user_id=current_user.id, latitude=lat, longitude=lon, type=inc_type, status='active')
        db.session.add(incident)
        db.session.commit()

        return jsonify({"status": "success", "data": {"message": "SOS alert created", "incident_id": incident.id}}), 201
    except HTTPException as e:
        return jsonify({"status": "error", "error": str(e.description)}), e.code
    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "error": str(e)}), 500

@user_bp.route('/api/incidents/user', methods=['GET'])
@token_required
def get_user_incidents(current_user):
    try:
        incidents = Incident.query.filter_by(user_id=current_user.id).order_by(Incident.id.desc()).all()
        data = [
            {
                "id": i.id, 
                "type": i.type, 
                "status": i.status, 
                "timestamp": i.timestamp.isoformat() if getattr(i, "timestamp", None) else None
            }
            for i in incidents
        ]
        return jsonify({"status": "success", "data": {"incidents": data}}), 200
    except HTTPException as e:
        return jsonify({"status": "error", "error": str(e.description)}), e.code
    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "error": str(e)}), 500

@user_bp.route('/api/zones/public', methods=['GET'])
@token_required
def get_public_zones(current_user):
    try:
        zones = GeoZone.query.limit(100).all()
        data = []
        for z in zones:
            data.append({
                "id": getattr(z, 'id', None),
                "name": getattr(z, 'name', 'Unknown Zone'),
                "latitude": float(z.latitude or 0.0),
                "longitude": float(z.longitude or 0.0),
                "radius": float(getattr(z, 'radius', 100) or 100),
                "risk_level": getattr(z, 'risk_level', 'LOW'),
                "type": getattr(z, 'type', 'RISK'),
                "place_type": getattr(z, 'place_type', 'general'),
                "description": getattr(z, 'description', ''),
                "avg_response_time": int(getattr(z, 'avg_response_time', 15) or 15)
            })
        return jsonify({"status": "success", "data": {"zones": data}}), 200
    except HTTPException as e:
        return jsonify({"status": "error", "error": str(e.description)}), e.code
    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "error": str(e)}), 500


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
        
        data = []
        for i in incidents:
            data.append({
                "id": getattr(i, 'id', None), 
                "user_id": getattr(i, 'user_id', None), 
                "latitude": float(i.latitude or 0.0), 
                "longitude": float(i.longitude or 0.0), 
                "type": getattr(i, 'type', 'unknown'), 
                "status": getattr(i, 'status', 'active'), 
                "timestamp": i.timestamp.isoformat() if getattr(i, "timestamp", None) else None
            })
            
        return jsonify({"status": "success", "data": {"incidents": data}}), 200
    except HTTPException as e:
        return jsonify({"status": "error", "error": str(e.description)}), e.code
    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "error": str(e)}), 500

@authority_bp.route('/api/incidents/<int:incident_id>', methods=['PUT'])
@token_required
@admin_required
def resolve_incident(current_user, incident_id):
    try:
        incident = Incident.query.get_or_404(incident_id, description="Incident not found")
        incident.status = 'resolved'
        db.session.commit()
        return jsonify({"status": "success", "data": {"message": "Incident resolved"}}), 200
    except HTTPException as e:
        return jsonify({"status": "error", "error": str(e.description)}), e.code
    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "error": str(e)}), 500

@authority_bp.route('/api/sos/heatmap', methods=['GET'])
@token_required
@admin_required
def get_sos_heatmap(current_user):
    try:
        incidents = Incident.query.filter_by(status='active').all()
        data = []
        for i in incidents:
            data.append({
                "latitude": float(i.latitude or 0.0), 
                "longitude": float(i.longitude or 0.0), 
                "intensity": 1.0
            })
        return jsonify({"status": "success", "data": data}), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "error": str(e)}), 500

@authority_bp.route('/api/geozones', methods=['POST', 'GET'])
@token_required
@admin_required
def manage_geozones(current_user):
    try:
        if request.method == 'POST':
            data = request.get_json()
            if not data:
                return jsonify({"status": "error", "error": "No JSON body provided"}), 400
                
            name = data.get('name')
            lat = data.get('latitude')
            lon = data.get('longitude')
            radius = data.get('radius')
            risk_level = data.get('risk_level')
            zone_type = data.get('type', 'RISK')
            place_type = data.get('place_type', 'general')
            description = data.get('description', '')
            try:
                avg_response_time = int(data.get('avg_response_time', 15))
            except (ValueError, TypeError):
                avg_response_time = 15
            
            if not name or lat is None or lon is None or radius is None or not risk_level:
                return jsonify({"status": "error", "error": "Missing required fields for GeoZone"}), 400
                
            is_valid, msg, lat, lon = validate_coordinates(lat, lon)
            if not is_valid:
                return jsonify({"status": "error", "error": msg}), 400
                
            try:
                radius = float(radius)
                if radius <= 0:
                    return jsonify({"status": "error", "error": "Radius must be strictly positive"}), 400
            except ValueError:
                return jsonify({"status": "error", "error": "Invalid radius format"}), 400
                
            if risk_level not in ["LOW", "MEDIUM", "HIGH"]:
                return jsonify({"status": "error", "error": "risk_level must be LOW, MEDIUM, or HIGH"}), 400
                
            if zone_type not in ["RISK", "RESTRICTED", "SAFE"]:
                return jsonify({"status": "error", "error": "type must be RISK, RESTRICTED, or SAFE"}), 400
                
            zone = GeoZone(
                name=name,
                latitude=lat,
                longitude=lon,
                radius=radius,
                risk_level=risk_level,
                type=zone_type,
                place_type=place_type,
                description=description,
                avg_response_time=avg_response_time
            )
            db.session.add(zone)
            db.session.commit()
            return jsonify({"status": "success", "data": {"message": "GeoZone added", "zone_id": zone.id}}), 201
        
        else: # GET
            zones = GeoZone.query.limit(100).all()
            data = []
            for z in zones:
                data.append({
                    "id": getattr(z, 'id', None),
                    "name": getattr(z, 'name', 'Unknown Zone'),
                    "latitude": float(z.latitude or 0.0),
                    "longitude": float(z.longitude or 0.0),
                    "radius": float(getattr(z, 'radius', 100) or 100),
                    "risk_level": getattr(z, 'risk_level', 'LOW'),
                    "type": getattr(z, 'type', 'RISK'),
                    "place_type": getattr(z, 'place_type', 'general'),
                    "description": getattr(z, 'description', ''),
                    "avg_response_time": int(getattr(z, 'avg_response_time', 15) or 15)
                })
            return jsonify({"status": "success", "data": {"geozones": data}}), 200
    except HTTPException as e:
        return jsonify({"status": "error", "error": str(e.description)}), e.code
    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "error": str(e)}), 500

@authority_bp.route('/api/geozones/<int:zone_id>', methods=['PUT', 'DELETE'])
@token_required
@admin_required
def modify_geozone(current_user, zone_id):
    try:
        zone = GeoZone.query.get_or_404(zone_id, description="Zone not found")
        
        if request.method == 'PUT':
            data = request.get_json()
            if not data:
                return jsonify({"status": "error", "error": "No JSON body provided"}), 400
                
            name = data.get('name')
            lat = data.get('latitude')
            lon = data.get('longitude')
            radius = data.get('radius')
            risk_level = data.get('risk_level')
            zone_type = data.get('type')
            
            if name: zone.name = name
            if lat is not None:
                try: zone.latitude = float(lat)
                except ValueError: return jsonify({"status": "error", "error": "Invalid latitude"}), 400
            if lon is not None:
                try: zone.longitude = float(lon)
                except ValueError: return jsonify({"status": "error", "error": "Invalid longitude"}), 400
            if radius is not None:
                try: 
                    radius = float(radius)
                    if radius <= 0: return jsonify({"status": "error", "error": "Radius must be strictly positive"}), 400
                    zone.radius = radius
                except ValueError: return jsonify({"status": "error", "error": "Invalid radius"}), 400
            if risk_level:
                if risk_level not in ["LOW", "MEDIUM", "HIGH"]:
                    return jsonify({"status": "error", "error": "Invalid risk level"}), 400
                zone.risk_level = risk_level
            if zone_type:
                if zone_type not in ["RISK", "RESTRICTED", "SAFE"]:
                    return jsonify({"status": "error", "error": "Invalid zone type"}), 400
                zone.type = zone_type
                
            db.session.commit()
            return jsonify({"status": "success", "data": {"message": "GeoZone updated"}}), 200
            
        elif request.method == 'DELETE':
            db.session.delete(zone)
            db.session.commit()
            return jsonify({"status": "success", "data": {"message": "Zone deleted"}}), 200
            
    except HTTPException as e:
        return jsonify({"status": "error", "error": str(e.description)}), e.code
    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "error": str(e)}), 500
