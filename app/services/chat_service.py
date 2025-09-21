from typing import List, Tuple, Set, Dict, Any
import re
from datetime import date
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.models import Booking, Trip, User


ALLOWED_PUBLIC_TOPICS = {
	"trip", "trips", "jadwal", "schedule", "promo", "promosi", "diskon", "blog", "artikel",
}
ALLOWED_PRIVATE_TOPICS = {
	"booking", "pesanan", "pesananku", "booking saya", "riwayat", "history"
}
SENSITIVE_KEYWORDS = {"password", "kata sandi", "token", "apikey", "api key"}


class ChatService:
	@staticmethod
	def classify_intent(message: str) -> str:
		msg = message.lower()
		if any(k in msg for k in SENSITIVE_KEYWORDS):
			return "sensitive"
		if any(k in msg for k in ALLOWED_PRIVATE_TOPICS):
			return "private"
		if any(k in msg for k in ALLOWED_PUBLIC_TOPICS):
			return "public"
		return "unknown"

	@staticmethod
	def build_public_context(db: Session) -> Tuple[List[str], List[str]]:
		chunks: List[str] = []
		keys: List[str] = []
		# Ambil beberapa trip published & aktif
		trips = (
			db.query(Trip)
			.filter(Trip.status == "published", Trip.is_active == 1)
			.order_by(Trip.id.desc())
			.limit(5)
			.all()
		)
		if trips:
			trip_lines = [
				f"Trip: {t.name} ({t.location}), durasi {t.duration}, harga {t.price}, status {t.status}"
				for t in trips
			]
			chunks.append("\n".join(trip_lines))
			keys.append("trips.published.latest5")
		return chunks, keys

	@staticmethod
	def _extract_keywords(message: str) -> List[str]:
		# Ambil token alfabet panjang >= 3 dan buang stopwords umum Indonesia
		raw = [w.lower() for w in re.findall(r"[A-Za-zA-ZÀ-ÿ]+", message)]
		stopwords = {
			"ada","apa","saja","hari","ini","yang","dan","atau","untuk","dengan","ke","di","itu","iya","dong","deh","ya","tolong","minta","info","tentang","berapa","kapan","dimana","mana"
		}
		return [w for w in raw if len(w) >= 3 and w not in stopwords]

	# ===== Structured helpers =====
	@staticmethod
	def search_trips(db: Session, message: str, limit: int = 10) -> List[Trip]:
		"""Kembalikan list Trip yang cocok dengan keyword pada pesan."""
		keywords = ChatService._extract_keywords(message)
		if not keywords:
			return []
		query = db.query(Trip).filter(Trip.is_active == 1)
		conditions = []
		for kw in keywords[:5]:
			like = f"%{kw}%"
			conditions.append(Trip.name.ilike(like))
			conditions.append(Trip.location.ilike(like))
			conditions.append(Trip.duration.ilike(like))
		if conditions:
			from sqlalchemy import or_
			query = query.filter(or_(*conditions))
		return query.order_by(Trip.id.desc()).limit(limit).all()

	@staticmethod
	def get_latest_published_trips(db: Session, limit: int = 5) -> List[Trip]:
		return (
			db.query(Trip)
			.filter(Trip.status == "published", Trip.is_active == 1)
			.order_by(Trip.id.desc())
			.limit(limit)
			.all()
		)

	@staticmethod
	def get_user_recent_bookings(db: Session, user: User, limit: int = 10) -> List[Booking]:
		return (
			db.query(Booking)
			.filter(Booking.customer_email == user.email)
			.order_by(Booking.created_at.desc())
			.limit(limit)
			.all()
		)

	@staticmethod
	def detect_booking_by_code(db: Session, user: User | None, message: str) -> Booking | None:
		m = re.search(r"\b([A-Z]{2}-?[A-Z0-9]{3,}|TG-[A-Z0-9]{6,})\b", message.upper())
		if not m:
			return None
		code = m.group(1)
		q = db.query(Booking).filter(Booking.booking_code == code)
		if user is not None:
			q = q.filter(Booking.customer_email == user.email)
		return q.first()

	@staticmethod
	def build_trip_search_context(db: Session, message: str) -> Tuple[List[str], List[str]]:
		"""Cari trip yang relevan berdasarkan keyword di pesan (nama, lokasi, durasi)."""
		chunks: List[str] = []
		keys: List[str] = []
		keywords = ChatService._extract_keywords(message)
		if not keywords:
			return chunks, keys
		
		# Bangun filter OR sederhana untuk nama/location/duration mengandung salah satu keyword
		query = db.query(Trip).filter(Trip.is_active == 1)
		conditions = []
		for kw in keywords[:5]:  # batasi hingga 5 keyword agar query ringan
			like = f"%{kw}%"
			conditions.append(Trip.name.ilike(like))
			conditions.append(Trip.location.ilike(like))
			conditions.append(Trip.duration.ilike(like))
		if conditions:
			from sqlalchemy import or_
			query = query.filter(or_(*conditions))
		
		results = query.order_by(Trip.id.desc()).limit(10).all()
		if results:
			lines = [
				f"Trip cocok: {t.name} ({t.location}), durasi {t.duration}, harga {t.price}, status {t.status}"
				for t in results
			]
			chunks.append("\n".join(lines))
			keys.append("trips.search.top10")
		return chunks, keys

	# ===== Additional cross-table contexts (raw SQL, no new models) =====
	@staticmethod
	def build_promos_context(db: Session, message: str) -> Tuple[List[str], List[str]]:
		chunks: List[str] = []
		keys: List[str] = []
		keywords = ChatService._extract_keywords(message)
		params = {}
		base = (
			"SELECT name, promo_code, discount_type, discount_value, is_active, start_date, end_date "
			"FROM promos WHERE is_active = 1 AND start_date <= NOW() AND end_date >= NOW()"
		)
		if keywords:
			# Filter sederhana untuk nama/description/promo_code
			like_clauses = []
			for i, kw in enumerate(keywords[:5]):
				param = f"kw{i}"
				params[param] = f"%{kw}%"
				like_clauses.append(
					"(name LIKE :{p} OR description LIKE :{p} OR promo_code LIKE :{p})".format(p=param)
				)
			base += " AND (" + " OR ".join(like_clauses) + ")"
		# MariaDB/MySQL tidak mendukung "NULLS LAST"; gunakan ekspresi IS NULL
		base += " ORDER BY is_featured DESC, (discount_value IS NULL) ASC, discount_value DESC LIMIT 10"
		rows = db.execute(text(base), params).fetchall()
		if rows:
			lines = []
			for r in rows:
				name, code, dtype, dval, active, start, end = r
				desc = f"Promo: {name}"
				if code:
					desc += f" (kode {code})"
				if dtype and dval is not None:
					desc += f", diskon {dtype}:{dval}"
				desc += f" periode {start} s/d {end}"
				lines.append(desc)
			chunks.append("\n".join(lines))
			keys.append("promos.active.today")
		return chunks, keys

	@staticmethod
	def build_blogs_context(db: Session, message: str) -> Tuple[List[str], List[str]]:
		chunks: List[str] = []
		keys: List[str] = []
		keywords = ChatService._extract_keywords(message)
		if not keywords:
			return chunks, keys
		params = {}
		base = (
			"SELECT title, slug FROM blogs WHERE status='published'"
		)
		like_clauses = []
		for i, kw in enumerate(keywords[:5]):
			param = f"kw{i}"
			params[param] = f"%{kw}%"
			like_clauses.append(
				"(title LIKE :{p} OR excerpt LIKE :{p})".format(p=param)
			)
		base += " AND (" + " OR ".join(like_clauses) + ") ORDER BY published_at DESC LIMIT 5"
		rows = db.execute(text(base), params).fetchall()
		if rows:
			lines = [f"Artikel: {title} (/{slug})" for (title, slug) in rows]
			chunks.append("\n".join(lines))
			keys.append("blogs.match.top5")
		return chunks, keys

	@staticmethod
	def build_schedules_context(db: Session, message: str) -> Tuple[List[str], List[str]]:
		# Tampilkan beberapa jadwal terdekat untuk trip 'published'
		chunks: List[str] = []
		keys: List[str] = []
		rows = db.execute(text(
			"""
			SELECT ts.trip_id, t.name, ts.departure_date, ts.return_date, ts.available_slots, ts.booked_slots, ts.status
			FROM trip_schedules ts
			JOIN trips t ON t.id = ts.trip_id
			WHERE t.status = 'published' AND t.is_active = 1 AND ts.departure_date >= CURDATE()
			ORDER BY ts.departure_date ASC
			LIMIT 5
			"""
		)).fetchall()
		if rows:
			lines = [
				f"Jadwal: {name}, berangkat {dep}, kembali {ret}, slot {avail-booked}/{avail} ({status})"
				for (_, name, dep, ret, avail, booked, status) in rows
			]
			chunks.append("\n".join(lines))
			keys.append("trip_schedules.upcoming.top5")
		return chunks, keys

	@staticmethod
	def build_facilities_context(db: Session, message: str) -> Tuple[List[str], List[str]]:
		chunks: List[str] = []
		keys: List[str] = []
		keywords = ChatService._extract_keywords(message)
		if not keywords:
			return chunks, keys
		params = {}
		base = "SELECT trip_id, name, type FROM trip_facilities WHERE 1=1"
		like_clauses = []
		for i, kw in enumerate(keywords[:5]):
			param = f"kw{i}"
			params[param] = f"%{kw}%"
			like_clauses.append("name LIKE :{p}".format(p=param))
		base += " AND (" + " OR ".join(like_clauses) + ") LIMIT 10"
		rows = db.execute(text(base), params).fetchall()
		if rows:
			lines = [f"Fasilitas trip#{tid}: {name} [{typ}]" for (tid, name, typ) in rows]
			chunks.append("\n".join(lines))
			keys.append("trip_facilities.match.top10")
		return chunks, keys

	@staticmethod
	def build_itineraries_context(db: Session, message: str) -> Tuple[List[str], List[str]]:
		chunks: List[str] = []
		keys: List[str] = []
		keywords = ChatService._extract_keywords(message)
		if not keywords:
			return chunks, keys
		params = {}
		base = "SELECT trip_id, day, title FROM trip_itineraries WHERE 1=1"
		like_clauses = []
		for i, kw in enumerate(keywords[:5]):
			param = f"kw{i}"
			params[param] = f"%{kw}%"
			like_clauses.append("(title LIKE :{p} OR description LIKE :{p})".format(p=param))
		base += " AND (" + " OR ".join(like_clauses) + ") ORDER BY trip_id, day LIMIT 10"
		rows = db.execute(text(base), params).fetchall()
		if rows:
			lines = [f"Itinerary trip#{tid} hari {d}: {title}" for (tid, d, title) in rows]
			chunks.append("\n".join(lines))
			keys.append("trip_itineraries.match.top10")
		return chunks, keys

	@staticmethod
	def build_reviews_context(db: Session, message: str) -> Tuple[List[str], List[str]]:
		chunks: List[str] = []
		keys: List[str] = []
		keywords = ChatService._extract_keywords(message)
		if not keywords:
			return chunks, keys
		params = {}
		base = "SELECT trip_id, reviewer_name, rating FROM reviews WHERE is_approved = 1"
		like_clauses = []
		for i, kw in enumerate(keywords[:5]):
			param = f"kw{i}"
			params[param] = f"%{kw}%"
			like_clauses.append("comment LIKE :{p}".format(p=param))
		base += " AND (" + " OR ".join(like_clauses) + ") ORDER BY rating DESC LIMIT 5"
		rows = db.execute(text(base), params).fetchall()
		if rows:
			lines = [f"Review trip#{tid} oleh {name}: rating {rating}" for (tid, name, rating) in rows]
			chunks.append("\n".join(lines))
			keys.append("reviews.match.top5")
		return chunks, keys

	@staticmethod
	def build_private_context(db: Session, user: User) -> Tuple[List[str], List[str]]:
		chunks: List[str] = []
		keys: List[str] = []
		# Booking milik user (dicocokkan via email user terhadap customer_email)
		bookings = (
			db.query(Booking)
			.filter(Booking.customer_email == user.email)
			.order_by(Booking.created_at.desc())
			.limit(10)
			.all()
		)
		if bookings:
			lines = []
			for b in bookings:
				trip_name = b.trip.name if b.trip else "-"
				lines.append(
					f"Booking {b.booking_code}: trip {trip_name}, tgl {b.departure_date}, peserta {b.participants}, total {b.total_amount}, status {b.status}/{b.payment_status}"
				)
			chunks.append("\n".join(lines))
			keys.append("bookings.mine.latest10")

		# Tambahkan ringkas profil user (tanpa data sensitif)
		profile_line = f"Profil: nama {user.name}, email {user.email}"
		chunks.append(profile_line)
		keys.append("users.me.profile")

		return chunks, keys

	@staticmethod
	def build_booking_by_code_context(db: Session, user: User | None, message: str) -> Tuple[List[str], List[str]]:
		"""Jika pesan berisi kode booking (mis. BK12345), tampilkan detailnya (dibatasi milik user)."""
		chunks: List[str] = []
		keys: List[str] = []
		m = re.search(r"\b([A-Z]{2}\d{3,})\b", message.upper())
		if not m:
			return chunks, keys
		code = m.group(1)
		q = db.query(Booking).filter(Booking.booking_code == code)
		if user is not None:
			q = q.filter(Booking.customer_email == user.email)
		b = q.first()
		if b:
			trip_name = b.trip.name if b.trip else "-"
			chunks.append(
				f"Detail Booking {b.booking_code}: trip {trip_name}, keberangkatan {b.departure_date}, peserta {b.participants}, total {b.total_amount}, status {b.status}, pembayaran {b.payment_status}"
			)
			keys.append("bookings.by_code")
		return chunks, keys

	@staticmethod
	def build_context(db: Session, user: User | None, message: str) -> Tuple[List[str], List[str], str]:
		intent = ChatService.classify_intent(message)
		if intent == "sensitive":
			return [], [], intent
		chunks: List[str] = []
		keys: List[str] = []

		# 1) Cross-table contexts (prioritaskan konten spesifik dulu)
		for builder in (
			ChatService.build_promos_context,
			ChatService.build_blogs_context,
			ChatService.build_schedules_context,
			ChatService.build_facilities_context,
			ChatService.build_itineraries_context,
			ChatService.build_reviews_context,
		):
			c, k = builder(db, message)
			chunks.extend(c)
			keys.extend(k)

		# 2) Pencarian trip berbasis keyword dari pesan
		c, k = ChatService.build_trip_search_context(db, message)
		chunks.extend(c)
		keys.extend(k)

		# 3) Jika masih kosong sama sekali, baru tampilkan trip publik terbaru sebagai fallback
		if not chunks:
			c, k = ChatService.build_public_context(db)
			chunks.extend(c)
			keys.extend(k)

		# Cross-table contexts (promos, blogs, schedules, facilities, itineraries, reviews)
		for builder in (
			ChatService.build_promos_context,
			ChatService.build_blogs_context,
			ChatService.build_schedules_context,
			ChatService.build_facilities_context,
			ChatService.build_itineraries_context,
			ChatService.build_reviews_context,
		):
			c, k = builder(db, message)
			chunks.extend(c)
			keys.extend(k)
		if intent == "private" and user is not None:
			c, k = ChatService.build_private_context(db, user)
			chunks.extend(c)
			keys.extend(k)

		# Detail booking berdasarkan kode (jika disebutkan)
		c, k = ChatService.build_booking_by_code_context(db, user, message)
		chunks.extend(c)
		keys.extend(k)
		return chunks, keys, intent

	# ===== AI Aggregation Flow =====
	ALLOWED_AI_TABLES: Set[str] = {
		"promos",
		"trips",
		"blogs",
		"trip_schedules",
		"trip_facilities",
		"trip_itineraries",
		"reviews",
	}

	@staticmethod
	def _extract_tables_in_sql(sql: str) -> Set[str]:
		import re as _re
		lower = sql.lower()
		tables: Set[str] = set()
		for pattern in [r"\bfrom\s+([a-zA-Z_][a-zA-Z0-9_]*)", r"\bjoin\s+([a-zA-Z_][a-zA-Z0-9_]*)"]:
			for m in _re.finditer(pattern, lower):
				tables.add(m.group(1))
		return tables

	@staticmethod
	def _is_select_only(sql: str) -> bool:
		lower = sql.strip().lower()
		if ";" in lower:
			return False
		blocked = ["update ", "insert ", "delete ", "drop ", "alter ", "truncate ", "create ", "grant ", "revoke "]
		if any(b in lower for b in blocked):
			return False
		# Disallow comments
		if "--" in lower or "/*" in lower or "*/" in lower:
			return False
		# Allow with-cte but must end up selecting
		return lower.startswith("select") or lower.startswith("with ")

	@staticmethod
	def _is_whitelisted_tables(sql: str, allowed: Set[str]) -> bool:
		tables = ChatService._extract_tables_in_sql(sql)
		return bool(tables) and tables.issubset(allowed)

	@staticmethod
	def _guess_main_table(sql: str) -> str | None:
		import re as _re
		m = _re.search(r"\bfrom\s+([a-zA-Z_][a-zA-Z0-9_]*)", sql.lower())
		return m.group(1) if m else None

	@staticmethod
	def build_ai_aggregate(db: Session, message: str, user: User | None) -> Tuple[List[str], List[str], Dict[str, Any]]:
		"""Bangun konteks dan hasil terkait berdasarkan query yang digenerate AI (SELECT-only).

		Return:
		- chunks: List[str] untuk konteks LLM
		- used_keys: List[str] untuk transparansi konteks
		- payload: dict { related_trips, related_promos, user_bookings, generated_queries }
		"""
		from app.services.gemini_service import GeminiService  # import lokal untuk hindari siklus
		from app.schemas import PromoSummary, TripResponse, BookingResponse

		chunks: List[str] = []
		used_keys: List[str] = []
		generated_queries: List[str] = []
		related_promos: List[PromoSummary] = []
		related_trips: List[TripResponse] = []
		user_bookings: List[BookingResponse] = []
		related_collections: Dict[str, List[dict]] = {}

		# 1) Dapatkan query dari AI
		ai_queries = GeminiService.generate_sql_queries(message, list(ChatService.ALLOWED_AI_TABLES))

		# 2) Validasi & eksekusi
		for q in ai_queries:
			q_str = q.strip()
			if not q_str:
				continue
			if not ChatService._is_select_only(q_str):
				continue
			if not ChatService._is_whitelisted_tables(q_str, ChatService.ALLOWED_AI_TABLES):
				continue
			main_table = ChatService._guess_main_table(q_str)
			try:
				rows = db.execute(text(q_str)).mappings().all()
				generated_queries.append(q_str)
				if not rows:
					continue
				rows_dicts = [dict(r) for r in rows]
				if main_table:
					related_collections.setdefault(main_table, []).extend(rows_dicts)
				# Kategorikan hasil
				if main_table == "promos":
					for r in rows:
						try:
							related_promos.append(PromoSummary(**dict(r)))
						except Exception:
							# Abaikan baris yang kolomnya tidak lengkap
							pass
					# Bangun konteks teks
					for r in rows:
						name = r.get("name")
						code = r.get("promo_code")
						desc = f"Promo: {name}"
						if code:
							desc += f" (kode {code})"
						chunks.append(desc)
					used_keys.append("promos.ai")
				elif main_table == "trips":
					for r in rows:
						try:
							related_trips.append(TripResponse(**dict(r)))
						except Exception:
							pass
					for r in rows:
						name = r.get("name")
						loc = r.get("location")
						price = r.get("price")
						chunks.append(f"Trip: {name} ({loc}), harga {price}")
					used_keys.append("trips.ai")
				else:
					# Tabel lain sebagai konteks naratif saja
					for r in rows:
						chunks.append(" | ".join([f"{k}:{v}" for k, v in dict(r).items()]))
					if main_table:
						used_keys.append(f"{main_table}.ai")
			except Exception:
				# Lewati query yang error
				continue

		# 3) Tambahkan konteks privat bila perlu & aman
		intent = ChatService.classify_intent(message)
		if intent == "private" and user is not None:
			try:
				bookings = ChatService.get_user_recent_bookings(db, user, limit=10)
				user_bookings = [BookingResponse.model_validate(b) for b in bookings]
				for b in bookings:
					trip_name = b.trip.name if b.trip else "-"
					chunks.append(
						f"Booking {b.booking_code}: trip {trip_name}, tgl {b.departure_date}, peserta {b.participants}, total {b.total_amount}, status {b.status}/{b.payment_status}"
					)
				used_keys.append("bookings.mine.latest10")
			except Exception:
				pass

		payload: Dict[str, Any] = dict(
			related_trips=related_trips,
			related_promos=related_promos,
			user_bookings=user_bookings,
			generated_queries=generated_queries,
			related_collections=related_collections,
		)
		return chunks, used_keys, payload

	@staticmethod
	def search_promos(db: Session, message: str, limit: int = 10) -> Tuple[List[dict], str]:
		"""Kembalikan promo aktif hari ini yang cocok dengan keyword (nama/desc/promo_code)."""
		keywords = ChatService._extract_keywords(message)
		params = {}
		base = (
			"SELECT name, promo_code, discount_type, discount_value, start_date, end_date, is_active "
			"FROM promos WHERE is_active = 1 AND start_date <= NOW() AND end_date >= NOW()"
		)
		if keywords:
			like_clauses = []
			for i, kw in enumerate(keywords[:5]):
				param = f"kw{i}"
				params[param] = f"%{kw}%"
				like_clauses.append(
					"(name LIKE :{p} OR description LIKE :{p} OR promo_code LIKE :{p})".format(p=param)
				)
			base += " AND (" + " OR ".join(like_clauses) + ")"
		base += " ORDER BY (discount_value IS NULL) ASC, discount_value DESC LIMIT :lim"
		params["lim"] = limit
		rows = db.execute(text(base), params).mappings().all()
		# Rekonstruksi SQL untuk debug/response sederhana (tanpa parameter binding engine)
		debug_sql = base
		for k, v in params.items():
			if isinstance(v, str):
				rep = v.replace("'", "''")
				debug_sql = debug_sql.replace(f":{k}", f"'{rep}'")
			else:
				debug_sql = debug_sql.replace(f":{k}", str(v))
		return [dict(r) for r in rows], debug_sql
