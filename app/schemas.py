from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Dict
from datetime import datetime, date
from decimal import Decimal


# ===== USER SCHEMAS =====
class UserBase(BaseModel):
	name: str
	email: EmailStr


class UserCreate(UserBase):
	password: str


class UserResponse(UserBase):
	id: int
	email_verified_at: Optional[datetime] = None
	created_at: Optional[datetime] = None
	updated_at: Optional[datetime] = None
	
	class Config:
		from_attributes = True


class UserProfile(UserResponse):
	bookings: List["BookingResponse"] = []


# ===== TRIP SCHEMAS =====
class TripBase(BaseModel):
	name: str
	slug: str
	location: str
	duration: str
	price: Decimal = Field(..., decimal_places=2)


class TripCreate(TripBase):
	status: str = "draft"
	is_active: int = 1


class TripResponse(TripBase):
	id: int
	status: str
	is_active: int
	
	class Config:
		from_attributes = True


# ===== BOOKING SCHEMAS =====
class BookingBase(BaseModel):
	customer_name: str
	customer_email: EmailStr
	customer_phone: str
	customer_age: Optional[int] = None
	emergency_contact_name: Optional[str] = None
	emergency_contact_phone: Optional[str] = None
	trip_type: str
	departure_date: date
	participants: int
	total_amount: Decimal = Field(..., decimal_places=2)


class BookingCreate(BookingBase):
	trip_id: int
	trip_schedule_id: Optional[int] = None
	promo_id: Optional[int] = None


class BookingResponse(BookingBase):
	id: int
	booking_code: str
	trip_id: int
	trip_schedule_id: Optional[int] = None
	promo_id: Optional[int] = None
	status: str
	payment_status: str
	created_at: Optional[datetime] = None
	updated_at: Optional[datetime] = None
	
	# Related data
	trip: Optional[TripResponse] = None
	user: Optional[UserResponse] = None
	
	class Config:
		from_attributes = True


class BookingDetail(BookingResponse):
	# Include trip details
	trip: TripResponse
	
	# Include user details if available
	user: Optional[UserResponse] = None


# ===== AUTH SCHEMAS =====
class LoginRequest(BaseModel):
	email: EmailStr
	password: str


class TokenResponse(BaseModel):
	access_token: str
	token_type: str = "bearer"
	user: UserResponse


# ===== CHAT SCHEMAS =====
class PromoSummary(BaseModel):
	name: str
	promo_code: str | None = None
	discount_type: str | None = None
	discount_value: Decimal | None = None
	start_date: datetime
	end_date: datetime
	is_active: int

class ChatRequest(BaseModel):
	message: str
	user_id: Optional[int] = None


class ChatResponse(BaseModel):
	reply: str
	used_context_keys: List[str] = []
	suggested_actions: List[str] = []
	related_trips: List[TripResponse] = []
	user_bookings: List[BookingResponse] = []
	related_promos: List["PromoSummary"] = []
	generated_queries: List[str] = []
	summary: str | None = None
	related_collections: Dict[str, List[dict]] = Field(default_factory=dict)



# ===== RESPONSE WRAPPERS =====
class SuccessResponse(BaseModel):
	success: bool = True
	message: str
	data: Optional[dict] = None


class ErrorResponse(BaseModel):
	success: bool = False
	message: str
	error_code: Optional[str] = None
	details: Optional[dict] = None


# ===== LIST RESPONSES =====
class UserListResponse(BaseModel):
	users: List[UserResponse]
	total: int
	page: int
	per_page: int


class TripListResponse(BaseModel):
	trips: List[TripResponse]
	total: int
	page: int
	per_page: int


class BookingListResponse(BaseModel):
	bookings: List[BookingResponse]
	total: int
	page: int
	per_page: int


# ===== SEARCH SCHEMAS =====
class TripSearchRequest(BaseModel):
	location: Optional[str] = None
	min_price: Optional[Decimal] = None
	max_price: Optional[Decimal] = None
	duration: Optional[str] = None
	status: Optional[str] = "published"


class BookingSearchRequest(BaseModel):
	user_email: Optional[EmailStr] = None
	booking_code: Optional[str] = None
	status: Optional[str] = None
	payment_status: Optional[str] = None
	departure_date_from: Optional[date] = None
	departure_date_to: Optional[date] = None


# ===== STATISTICS SCHEMAS =====
class BookingStats(BaseModel):
	total_bookings: int
	pending_bookings: int
	confirmed_bookings: int
	paid_bookings: int
	cancelled_bookings: int
	completed_bookings: int
	total_revenue: Decimal


class TripStats(BaseModel):
	total_trips: int
	active_trips: int
	published_trips: int
	average_price: Decimal
	popular_locations: List[dict]


# Update forward references
UserProfile.model_rebuild()
BookingResponse.model_rebuild()
BookingDetail.model_rebuild()
ChatResponse.model_rebuild()
