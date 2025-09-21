from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas import (
	ChatRequest, ChatResponse, BookingListResponse, BookingResponse,
	SuccessResponse, ErrorResponse, TripResponse, UserProfile, PromoSummary
)
from app.services.auth_service import AuthService
from app.services.chat_service import ChatService
from app.services.gemini_service import GeminiService
from app.db.models import Booking

router = APIRouter(prefix="", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, db: Session = Depends(get_db), user=Depends(AuthService.get_current_user)):
	# Tentukan intent terlebih dahulu untuk gating
	intent = ChatService.classify_intent(payload.message)
	if intent == "sensitive":
		return ChatResponse(reply="Akses ditolak. Jangan meminta data sensitif seperti password atau token.", used_context_keys=[])
	if intent == "private" and user is None:
		return ChatResponse(reply="Silakan login untuk mengakses informasi pribadi seperti booking Anda.", used_context_keys=[])
	# Enforce tema travel secara global
	if not ChatService.is_on_theme(payload.message):
		return ChatResponse(
			reply="Maaf, topik di luar tema travel. Ajukan pertanyaan seputar promo, trip, itinerary, keamanan perjalanan, dsb.",
			used_context_keys=[],
		)

	# Agregasi hasil sekali jalan berbasis query AI
	chunks, keys, agg = ChatService.build_ai_aggregate(db=db, message=payload.message, user=user)
	related_trips = agg.get("related_trips", [])
	related_promos = agg.get("related_promos", [])
	user_bookings = agg.get("user_bookings", [])
	generated_queries = agg.get("generated_queries", [])
	related_collections = agg.get("related_collections", {})

	# Suggested actions
	suggested_actions: list[str] = []
	for p in related_promos:
		if getattr(p, "promo_code", None):
			suggested_actions.append(f"Gunakan kode {p.promo_code}")
	if related_trips:
		suggested_actions.append("Lihat detail trip yang direkomendasikan")
	if user_bookings:
		suggested_actions.append("Lihat detail booking terakhir Anda")

	# Jika tidak ada konteks sama sekali
	if not chunks:
		# Coba respons general bertema travel untuk intent public/unknown atau tips tematik
		if intent in ("public", "unknown") or ChatService.is_thematic_allowed(payload.message):
			reply = GeminiService.answer_thematic(user_message=payload.message)
			keys.append("general.ai")
			summary = _build_general_summary(
				message=payload.message,
				reply=reply,
				related_trips=related_trips,
				related_promos=related_promos,
				user_bookings=user_bookings,
			)
			return ChatResponse(
				reply=reply,
				used_context_keys=keys,
				suggested_actions=suggested_actions,
				related_trips=related_trips,
				user_bookings=user_bookings,
				related_promos=related_promos,
				generated_queries=generated_queries,
				summary=summary,
				related_collections=related_collections,
			)
		# Jika topik tidak diizinkan → tetap tolak
		summary = _build_general_summary(
			message=payload.message,
			reply="Maaf, pertanyaan di luar konteks database ini.",
			related_trips=related_trips,
			related_promos=related_promos,
			user_bookings=user_bookings,
		)
		return ChatResponse(
			reply="Maaf, pertanyaan di luar konteks database ini.",
			used_context_keys=keys,
			suggested_actions=suggested_actions,
			related_trips=related_trips,
			user_bookings=user_bookings,
			related_promos=related_promos,
			generated_queries=generated_queries,
			summary=summary,
			related_collections=related_collections,
		)

	reply = GeminiService.answer_with_context(user_message=payload.message, context_chunks=chunks)
	summary = _build_general_summary(
		message=payload.message,
		reply=reply,
		related_trips=related_trips,
		related_promos=related_promos,
		user_bookings=user_bookings,
	)
	return ChatResponse(
		reply=reply,
		used_context_keys=keys,
		suggested_actions=suggested_actions,
		related_trips=related_trips,
		user_bookings=user_bookings,
		related_promos=related_promos,
		generated_queries=generated_queries,
		summary=summary,
		related_collections=related_collections,
	)


def _build_general_summary(
	*,
	message: str,
	reply: str,
	related_trips: list,
	related_promos: list,
	user_bookings: list,
) -> str:
	"""Bangun ringkasan naratif singkat berbasis request+response tanpa listing item satu per satu."""
	parts: list[str] = []
	msg = message.strip()
	if msg:
		parts.append(f"Permintaan: {msg}")
	# Promos
	if related_promos:
		parts.append(f"Ditemukan {len(related_promos)} promo aktif yang relevan.")
	# Trips
	if related_trips:
		parts.append(f"Ada {len(related_trips)} trip yang sesuai konteks.")
	# Bookings
	if user_bookings:
		parts.append(f"Kami juga menemukan {len(user_bookings)} booking terkait akun Anda.")
	# Jawaban
	if reply:
		parts.append(f"Jawaban: {reply}")
	# Gabungkan menjadi 2-4 kalimat ringkas
	return " ".join(parts)


@router.get("/me/bookings", response_model=BookingListResponse)
def my_bookings(
	db: Session = Depends(get_db), 
	user=Depends(AuthService.get_current_user),
	page: int = 1,
	per_page: int = 20
):
	"""Get user's bookings with pagination"""
	if user is None:
		return BookingListResponse(bookings=[], total=0, page=page, per_page=per_page)

	try:
		# Calculate offset for pagination
		offset = (page - 1) * per_page
		
		# Get total count
		total = db.query(Booking).filter(Booking.customer_email == user.email).count()
		
		# Get bookings with pagination
		bookings = (
			db.query(Booking)
			.filter(Booking.customer_email == user.email)
			.order_by(Booking.created_at.desc())
			.offset(offset)
			.limit(per_page)
			.all()
		)
		
		# Convert to response format
		booking_responses = []
		for booking in bookings:
			booking_responses.append(BookingResponse.model_validate(booking))
		
		return BookingListResponse(
			bookings=booking_responses,
			total=total,
			page=page,
			per_page=per_page
		)
		
	except Exception as e:
		raise HTTPException(status_code=500, detail=f"Error retrieving bookings: {str(e)}")


@router.get("/me/profile", response_model=UserProfile)
def get_user_profile(
	db: Session = Depends(get_db),
	user=Depends(AuthService.get_current_user)
):
	"""Get user profile with bookings"""
	if user is None:
		raise HTTPException(status_code=401, detail="Authentication required")
	
	try:
		# Get user's recent bookings
		bookings = (
			db.query(Booking)
			.filter(Booking.customer_email == user.email)
			.order_by(Booking.created_at.desc())
			.limit(10)
			.all()
		)
		
		# Convert to response format
		booking_responses = [BookingResponse.model_validate(booking) for booking in bookings]
		
		# Create user profile
		user_profile = UserProfile.model_validate(user)
		user_profile.bookings = booking_responses
		
		return user_profile
		
	except Exception as e:
		raise HTTPException(status_code=500, detail=f"Error retrieving profile: {str(e)}")
