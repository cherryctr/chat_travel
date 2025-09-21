import google.generativeai as genai
from typing import List
import json
import re

from app.core.config import settings


class GeminiService:
	_initialized = False

	@classmethod
	def _ensure_init(cls):
		if cls._initialized:
			return
		if not settings.google_api_key:
			raise RuntimeError("GOOGLE_API_KEY belum diatur")
		genai.configure(api_key=settings.google_api_key)
		cls._initialized = True

	@classmethod
	def answer_with_context(cls, user_message: str, context_chunks: List[str]) -> str:
		cls._ensure_init()
		model_name = settings.gemini_model
		model = genai.GenerativeModel(model_name)

		instructions = (
			"Anda adalah asisten TravelGO. Jawab HANYA berdasarkan konteks berikut. "
			"Jika tidak ada jawaban dalam konteks, jawab: 'Maaf, pertanyaan di luar konteks database ini.' "
			"Jangan mengarang, jangan gunakan pengetahuan luar. Jawaban harus singkat dan dalam bahasa Indonesia."
		)
		context_text = "\n\n".join(context_chunks) if context_chunks else "(tidak ada konteks yang relevan)"
		prompt = f"{instructions}\n\nKONTEKS:\n{context_text}\n\nPERTANYAAN PENGGUNA:\n{user_message}"

		resp = model.generate_content(prompt)
		return resp.text.strip() if hasattr(resp, "text") and resp.text else "Maaf, pertanyaan di luar konteks database ini."

	@classmethod
	def generate_sql_queries(cls, user_message: str, allowed_tables: List[str]) -> List[str]:
		"""Minta model menghasilkan daftar query SELECT-only terhadap tabel whitelist.

		Output diharapkan berupa JSON array: [{"table":"promos","sql":"SELECT ..."}, ...].
		Jika parsing gagal, gunakan fallback heuristik sederhana.
		"""
		cls._ensure_init()
		model_name = settings.gemini_model
		model = genai.GenerativeModel(model_name)

		allowed = ", ".join(allowed_tables)
		msg_lower = user_message.lower()
		# Petunjuk waktu dinamis: hanya tambahkan filter tanggal saat diminta
		date_hint = (
			"JANGAN menambahkan filter tanggal (start_date/end_date) kecuali pengguna memintanya secara eksplisit. "
		)
		if "hari ini" in msg_lower:
			date_hint = (
				"Tambahkan filter tanggal untuk HARI INI: gunakan periode aktif yang mencakup hari ini, misalnya "
				"start_date <= NOW() AND end_date >= NOW(). "
			)
		elif "bulan ini" in msg_lower:
			date_hint = (
				"Tambahkan filter tanggal untuk BULAN INI: gunakan pembatas bulan berjalan, misalnya "
				"(MONTH(start_date) = MONTH(CURDATE()) OR MONTH(end_date) = MONTH(CURDATE())) AND YEAR(start_date) = YEAR(CURDATE()). "
			)
		elif "tahun ini" in msg_lower:
			date_hint = (
				"Tambahkan filter tanggal untuk TAHUN INI: gunakan pembatas tahun berjalan, misalnya "
				"(YEAR(start_date) = YEAR(CURDATE()) OR YEAR(end_date) = YEAR(CURDATE())). "
			)

		instructions = (
			"Anda adalah asisten pembuat SQL untuk aplikasi TravelGO. "
			"Buat 1-3 query SQL SELECT-only, TANPA DDL/DML, TANPA komentar, TANPA multi-statement. "
			"WAJIB hanya menggunakan tabel berikut: " + allowed + ". "
			"Gunakan kolom yang sesuai skema berikut jika relevan:\n"
			"- promos: name, promo_code, discount_type, discount_value, start_date, end_date, is_active\n"
			"- trips: id, name, slug, location, duration, price, status, is_active\n"
			"- blogs: title, slug\n"
			"- trip_schedules: trip_id, departure_date, return_date, available_slots, booked_slots, status\n"
			"- trip_facilities: trip_id, name, type\n"
			"- trip_itineraries: trip_id, day, title\n"
			"- reviews: trip_id, reviewer_name, rating\n"
			"Untuk promos, sertakan kolom start_date, end_date, is_active agar lengkap. "
			+ date_hint +
			"Format jawaban HANYA JSON valid (tanpa penjelasan): [{\"table\":\"...\",\"sql\":\"...\"}]."
		)
		prompt = (
			instructions
			+ "\n\nPesan pengguna: \n" + user_message
		)

		try:
			resp = model.generate_content(prompt)
			text = resp.text if hasattr(resp, "text") and resp.text else "[]"
			# Bersihkan code fences jika ada
			text = re.sub(r"^```[a-zA-Z]*", "", text.strip())
			text = re.sub(r"```$", "", text.strip())
			data = json.loads(text)
			queries: List[str] = []
			if isinstance(data, list):
				for item in data:
					if isinstance(item, dict) and "sql" in item:
						q = str(item["sql"]).strip()
						if q:
							queries.append(q)
			return queries
		except Exception:
			pass

		# Fallback sederhana jika model gagal/format tidak sesuai
		msg = user_message.lower()
		fallbacks: List[str] = []
		if "promo" in msg:
			promo_sql = (
				"SELECT name, promo_code, discount_type, discount_value, start_date, end_date, is_active "
				"FROM promos WHERE is_active = 1"
			)
			# Tambah filter tanggal hanya jika diminta
			if "hari ini" in msg:
				promo_sql += " AND start_date <= NOW() AND end_date >= NOW()"
			elif "bulan ini" in msg:
				promo_sql += " AND ((MONTH(start_date)=MONTH(CURDATE()) AND YEAR(start_date)=YEAR(CURDATE())) OR (MONTH(end_date)=MONTH(CURDATE()) AND YEAR(end_date)=YEAR(CURDATE())))"
			elif "tahun ini" in msg:
				promo_sql += " AND (YEAR(start_date)=YEAR(CURDATE()) OR YEAR(end_date)=YEAR(CURDATE()))"
			promo_sql += " ORDER BY (discount_value IS NULL) ASC, discount_value DESC LIMIT 10"
			fallbacks.append(promo_sql)
		if any(k in msg for k in ["trip", "trips", "jadwal", "schedule", "bali", "labuan", "raja amp" ]):
			fallbacks.append(
				"SELECT id, name, slug, location, duration, price, status, is_active "
				"FROM trips WHERE is_active = 1 AND status = 'published' ORDER BY id DESC LIMIT 10"
			)
		return fallbacks
