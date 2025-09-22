from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import time
import random
import html as _html
from fastapi.responses import StreamingResponse

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



def _format_reply_html(text: str) -> str:
	# Ubah teks menjadi HTML: dukung paragraf, bullet (-/*/•) dan numbered list (1. / 1)
	lines = (text or "").splitlines()
	parts: list[str] = []
	list_mode = None  # 'ul' | 'ol' | None
	def close_list():
		nonlocal list_mode
		if list_mode == 'ul':
			parts.append("</ul>")
		elif list_mode == 'ol':
			parts.append("</ol>")
		list_mode = None
	for raw in lines:
		line = raw.strip()
		if not line:
			# break paragraph or list
			close_list()
			continue
		# bullets
		if line.startswith(('- ', '* ', '• ')):
			content = line[2:] if line[0] in ('-', '*') else line[1:].strip()
			if list_mode != 'ul':
				close_list()
				parts.append("<ul>")
				list_mode = 'ul'
			parts.append(f"<li>{_html.escape(content)}</li>")
			continue
		# numbered
		import re as _re
		m = _re.match(r"^(\d+)[\.)]\s+(.*)$", line)
		if m:
			content = m.group(2)
			if list_mode != 'ol':
				close_list()
				parts.append("<ol>")
				list_mode = 'ol'
			parts.append(f"<li>{_html.escape(content)}</li>")
			continue
		# paragraph
		close_list()
		parts.append(f"<p>{_html.escape(line)}</p>")
	close_list()
	return ''.join(parts)


def _format_html(resp: ChatResponse) -> str:
	parts: list[str] = []
	# Reply utama
	parts.append(_format_reply_html(resp.reply))
	# Suggested actions
	if resp.suggested_actions:
		items = ''.join([f"<li>{_html.escape(a)}</li>" for a in resp.suggested_actions])
		parts.append(f"<ul>{items}</ul>")
	# Related promos minimal
	if resp.related_promos:
		promo_items = []
		for p in resp.related_promos[:5]:
			name = getattr(p, 'name', '')
			code = getattr(p, 'promo_code', None) or ''
			promo_items.append(f"<li>{_html.escape(name)}{(' ('+_html.escape(code)+')') if code else ''}</li>")
		parts.append(f"<div><strong>Promo terkait:</strong><ul>{''.join(promo_items)}</ul></div>")
	# Related trips minimal
	if resp.related_trips:
		trip_items = []
		for t in resp.related_trips[:5]:
			name = getattr(t, 'name', '')
			loc = getattr(t, 'location', '')
			trip_items.append(f"<li>{_html.escape(name)} - {_html.escape(loc)}</li>")
		parts.append(f"<div><strong>Trip terkait:</strong><ul>{''.join(trip_items)}</ul></div>")
	return ''.join(parts)


@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, db: Session = Depends(get_db)):
	# Tentukan intent terlebih dahulu untuk gating
	intent = ChatService.classify_intent(payload.message)
	if intent == "sensitive":
		return ChatResponse(reply="Akses ditolak. Jangan meminta data sensitif seperti password atau token.", used_context_keys=[])

	# Tolak akses data internal
	if ChatService.is_internal_data_request(payload.message):
		return ChatResponse(
			reply="Data internal sistem tidak dapat diakses.",
			used_context_keys=[],
		)

	# Sapaan sederhana: balas sapaan jika murni salam, selain itu lanjutkan alur normal
	if ChatService.is_pure_greeting(payload.message):
		return ChatResponse(
			reply=ChatService.build_greeting_reply(),
			used_context_keys=["greeting"],
		)

	# Tolak pencarian PII (nama/email/telepon) tanpa kode booking demi privasi
	if ChatService.is_pii_lookup(payload.message) and not ChatService._extract_booking_code(payload.message, getattr(payload, "booking_code", None)):
		return ChatResponse(
			reply="Demi privasi, pencarian berdasarkan nama/email/telepon tidak diizinkan. Untuk pemeriksaan, gunakan KODE BOOKING (mis. TG-ABC123).",
			used_context_keys=[],
		)

	# Gating promo spesifik: jika user ingin cek status/valid/detail promo tapi tidak menyebut kode
	if ChatService.needs_promo_identifier(payload.message):
		promo_code = ChatService._extract_promo_code(db, payload.message)
		if not promo_code:
			return ChatResponse(
				reply="Untuk memeriksa promo spesifik, sebutkan KODE PROMO (mis. WELCOME200).",
				used_context_keys=[],
			)
		# Validasi keberadaan kode promo
		from sqlalchemy import text as _text
		row = db.execute(_text("SELECT 1 FROM promos WHERE promo_code = :c LIMIT 1"), {"c": promo_code}).fetchone()
		if not row:
			return ChatResponse(
				reply=f"Kode promo {promo_code} tidak ditemukan. Periksa ejaan atau gunakan kode lain.",
				used_context_keys=["promos.by_code"],
			)

	# Gating trip spesifik: minta id/slug saat cek status/detail
	if ChatService.needs_trip_identifier(payload.message):
		slug, trip_id = ChatService._extract_trip_slug_or_id(db, payload.message)
		if not slug and not trip_id:
			return ChatResponse(
				reply="Untuk melihat status/detail trip, sebutkan ID atau SLUG trip (mis. 'raja-ampat-diving-paradise').",
				used_context_keys=[],
			)
		# Validasi keberadaan
		if slug:
			from sqlalchemy import text as _text
			row = db.execute(_text("SELECT 1 FROM trips WHERE slug = :s LIMIT 1"), {"s": slug}).fetchone()
			if not row:
				return ChatResponse(
					reply=f"Trip '{slug}' tidak ditemukan.",
					used_context_keys=["trips.by_slug"],
				)
		# trip_id via ORM sudah tervalidasi di extractor

	# Gating blog spesifik: minta slug saat cek status/detail artikel
	if ChatService.needs_blog_identifier(payload.message):
		blog_slug = ChatService._extract_blog_slug(db, payload.message)
		if not blog_slug:
			return ChatResponse(
				reply="Untuk melihat detail artikel, sebutkan SLUG artikel (mis. '10-tips-budget-travel-untuk-backpacker-pemula').",
				used_context_keys=[],
			)
		from sqlalchemy import text as _text
		row = db.execute(_text("SELECT 1 FROM blogs WHERE slug = :s LIMIT 1"), {"s": blog_slug}).fetchone()
		if not row:
			return ChatResponse(
				reply=f"Artikel '{blog_slug}' tidak ditemukan.",
				used_context_keys=["blogs.by_slug"],
			)

	# Gating category spesifik: minta slug saat cek status/detail kategori
	if ChatService.needs_category_identifier(payload.message):
		cat_slug = ChatService._extract_category_slug(db, payload.message)
		if not cat_slug:
			return ChatResponse(
				reply="Untuk melihat detail kategori, sebutkan SLUG kategori (mis. 'tips-travel').",
				used_context_keys=[],
			)
		from sqlalchemy import text as _text
		row = db.execute(_text("SELECT 1 FROM categories WHERE slug = :s LIMIT 1"), {"s": cat_slug}).fetchone()
		if not row:
			return ChatResponse(
				reply=f"Kategori '{cat_slug}' tidak ditemukan.",
				used_context_keys=["categories.by_slug"],
			)

	# Gating tag spesifik: minta slug saat cek status/detail tag
	if ChatService.needs_tag_identifier(payload.message):
		tag_slug = ChatService._extract_tag_slug(db, payload.message)
		if not tag_slug:
			return ChatResponse(
				reply="Untuk melihat detail tag, sebutkan SLUG tag (mis. 'budgettravel').",
				used_context_keys=[],
			)
		from sqlalchemy import text as _text
		row = db.execute(_text("SELECT 1 FROM tags WHERE slug = :s LIMIT 1"), {"s": tag_slug}).fetchone()
		if not row:
			return ChatResponse(
				reply=f"Tag '{tag_slug}' tidak ditemukan.",
				used_context_keys=["tags.by_slug"],
			)

	# Gating schedule spesifik: minta trip id/slug saat cek status/detail jadwal
	if ChatService.needs_schedule_identifier(payload.message):
		slug, trip_id = ChatService._extract_trip_slug_or_id(db, payload.message)
		if not slug and not trip_id:
			return ChatResponse(
				reply="Untuk melihat jadwal trip, sebutkan ID atau SLUG trip (mis. 'raja-ampat-diving-paradise').",
				used_context_keys=[],
			)

	# Gating review spesifik: minta id saat cek status/detail
	if ChatService.needs_review_identifier(payload.message):
		review_id = ChatService._extract_review_id(db, payload.message)
		if not review_id:
			return ChatResponse(
				reply="Untuk memeriksa detail review, sebutkan ID review (mis. 'review #5').",
				used_context_keys=[],
			)
		from sqlalchemy import text as _text
		row = db.execute(_text("SELECT 1 FROM reviews WHERE id = :i LIMIT 1"), {"i": review_id}).fetchone()
		if not row:
			return ChatResponse(
				reply=f"Review #{review_id} tidak ditemukan.",
				used_context_keys=["reviews.by_id"],
			)
	# Private data requires explicit identifier (message contains private topic or intent detected)
	if (intent == "private" or ChatService.is_private_topic(payload.message)):
		# Cek ada/tidaknya identifier (kode booking)
		subintent = ChatService.detect_private_subintent(payload.message)
		code = ChatService._extract_booking_code(payload.message, getattr(payload, "booking_code", None))
		if not code:
			instruksi = "Untuk memeriksa status booking, sebutkan KODE BOOKING Anda (mis. TG-ABC123)."
			if subintent == "payment_status":
				instruksi = "Untuk memeriksa status pembayaran, sebutkan KODE BOOKING Anda (mis. TG-ABC123)."
			elif subintent == "booking_detail":
				instruksi = "Untuk melihat detail booking, sebutkan KODE BOOKING Anda (mis. TG-ABC123)."
			return ChatResponse(
				reply=instruksi,
				used_context_keys=[]
			)
		# Jika ada kode, pastikan valid (ada di DB). Jika tidak ada → balas khusus tanpa fallback AI
		b = db.query(Booking).filter(Booking.booking_code == code).first()
		if b is None:
			return ChatResponse(
				reply=f"Kode booking {code} tidak ditemukan. Periksa ejaan atau gunakan kode lain.",
				used_context_keys=["bookings.by_code"],
			)
	# Enforce tema travel secara global
	if not ChatService.is_on_theme(payload.message):
		return ChatResponse(
			reply="Maaf, topik di luar tema travel. Ajukan pertanyaan seputar promo, trip, itinerary, keamanan perjalanan, dsb.",
			used_context_keys=[],
		)

	# Agregasi hasil sekali jalan berbasis query AI
	chunks, keys, agg = ChatService.build_ai_aggregate(db=db, message=payload.message, user=None, booking_code=getattr(payload, "booking_code", None))
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

	# Ada konteks: jawab dengan memanfaatkan chunks
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


@router.post("/chat/stream")
def chat_stream(payload: ChatRequest, db: Session = Depends(get_db)):
	def gen():
		# Delay 5 detik sebelum stream
		time.sleep(5)
		# Proses menggunakan handler normal (tanpa delay tambahan)
		resp = chat(payload, db)
		# Stream per paragraf/list item
		lines = (resp.reply or "").splitlines()
		list_mode = None
		import re as _re
		def close_list_stream():
			nonlocal list_mode
			if list_mode:
				yield f"data: </{list_mode}>\n\n"
				list_mode = None
		for raw in lines:
			line = raw.strip()
			if not line:
				# break paragraph or list
				if list_mode:
					yield from close_list_stream()
				continue
			# bullets
			if line.startswith(('- ', '* ', '• ')):
				content = line[2:] if line[0] in ('-', '*') else line[1:].strip()
				if list_mode != 'ul':
					if list_mode:
						yield from close_list_stream()
					yield "data: <ul>\n\n"
					list_mode = 'ul'
				yield "data: <li>\n\n"
				for ch in _html.escape(content):
					yield f"data: {ch}\n\n"
					time.sleep(random.uniform(0.01, 0.025))
				yield "data: </li>\n\n"
				continue
			# numbered
			m = _re.match(r"^(\d+)[\.)]\s+(.*)$", line)
			if m:
				content = m.group(2)
				if list_mode != 'ol':
					if list_mode:
						yield from close_list_stream()
					yield "data: <ol>\n\n"
					list_mode = 'ol'
				yield "data: <li>\n\n"
				for ch in _html.escape(content):
					yield f"data: {ch}\n\n"
					time.sleep(random.uniform(0.01, 0.025))
				yield "data: </li>\n\n"
				continue
			# paragraph
			if list_mode:
				yield from close_list_stream()
			yield "data: <p>\n\n"
			for ch in _html.escape(line):
				yield f"data: {ch}\n\n"
				time.sleep(random.uniform(0.01, 0.025))
			yield "data: </p>\n\n"
		if list_mode:
			yield from close_list_stream()
		# Kirim bagian lain (actions/promos/trips) sebagai blok HTML siap pakai
		rest_html = ''.join(_format_html(ChatResponse(
			reply="",
			used_context_keys=resp.used_context_keys,
			suggested_actions=resp.suggested_actions,
			related_trips=resp.related_trips,
			user_bookings=resp.user_bookings,
			related_promos=resp.related_promos,
			generated_queries=resp.generated_queries,
			related_collections=resp.related_collections,
		)) )
		if rest_html:
			yield f"data: {rest_html}\n\n"
	return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


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
