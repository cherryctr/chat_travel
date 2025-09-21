from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.db.session import get_db
from app.schemas import (
	TripResponse, TripListResponse, TripSearchRequest,
	SuccessResponse, ErrorResponse
)
from app.db.models import Trip
from decimal import Decimal

router = APIRouter(prefix="/trips", tags=["trips"])


@router.get("/", response_model=TripListResponse)
def get_trips(
	db: Session = Depends(get_db),
	page: int = Query(1, ge=1),
	per_page: int = Query(20, ge=1, le=100),
	location: Optional[str] = None,
	min_price: Optional[float] = None,
	max_price: Optional[float] = None,
	duration: Optional[str] = None,
	status: str = "published"
):
	"""Get trips with filtering and pagination"""
	try:
		# Build query
		query = db.query(Trip).filter(Trip.is_active == 1)
		
		# Apply filters
		if status:
			query = query.filter(Trip.status == status)
		if location:
			query = query.filter(Trip.location.ilike(f"%{location}%"))
		if min_price:
			query = query.filter(Trip.price >= Decimal(str(min_price)))
		if max_price:
			query = query.filter(Trip.price <= Decimal(str(max_price)))
		if duration:
			query = query.filter(Trip.duration.ilike(f"%{duration}%"))
		
		# Get total count
		total = query.count()
		
		# Apply pagination
		offset = (page - 1) * per_page
		trips = query.offset(offset).limit(per_page).all()
		
		# Convert to response format
		trip_responses = [TripResponse.model_validate(trip) for trip in trips]
		
		return TripListResponse(
			trips=trip_responses,
			total=total,
			page=page,
			per_page=per_page
		)
		
	except Exception as e:
		raise HTTPException(status_code=500, detail=f"Error retrieving trips: {str(e)}")


@router.get("/{trip_id}", response_model=TripResponse)
def get_trip(trip_id: int, db: Session = Depends(get_db)):
	"""Get trip by ID"""
	try:
		trip = db.query(Trip).filter(Trip.id == trip_id, Trip.is_active == 1).first()
		if not trip:
			raise HTTPException(status_code=404, detail="Trip not found")
		
		return TripResponse.model_validate(trip)
		
	except HTTPException:
		raise
	except Exception as e:
		raise HTTPException(status_code=500, detail=f"Error retrieving trip: {str(e)}")


@router.get("/search/", response_model=TripListResponse)
def search_trips(
	search_request: TripSearchRequest,
	db: Session = Depends(get_db),
	page: int = Query(1, ge=1),
	per_page: int = Query(20, ge=1, le=100)
):
	"""Search trips with advanced filtering"""
	try:
		# Build query
		query = db.query(Trip).filter(Trip.is_active == 1)
		
		# Apply search filters
		if search_request.status:
			query = query.filter(Trip.status == search_request.status)
		if search_request.location:
			query = query.filter(Trip.location.ilike(f"%{search_request.location}%"))
		if search_request.min_price:
			query = query.filter(Trip.price >= search_request.min_price)
		if search_request.max_price:
			query = query.filter(Trip.price <= search_request.max_price)
		if search_request.duration:
			query = query.filter(Trip.duration.ilike(f"%{search_request.duration}%"))
		
		# Get total count
		total = query.count()
		
		# Apply pagination
		offset = (page - 1) * per_page
		trips = query.offset(offset).limit(per_page).all()
		
		# Convert to response format
		trip_responses = [TripResponse.model_validate(trip) for trip in trips]
		
		return TripListResponse(
			trips=trip_responses,
			total=total,
			page=page,
			per_page=per_page
		)
		
	except Exception as e:
		raise HTTPException(status_code=500, detail=f"Error searching trips: {str(e)}")
