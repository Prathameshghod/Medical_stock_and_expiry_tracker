from datetime import datetime, timedelta
import heapq
from bisect import bisect_left, bisect_right
from flask import Flask, render_template, request, redirect, url_for, flash

app = Flask(__name__)
app.secret_key = "dev-secret-key"  # For flash messages

# ------------------------------
# In-memory DSA-backed datastore
# ------------------------------
# medicines: dict[str, list[dict]]
# Each batch: {"batch_id": str, "expiry": "YYYY-MM-DD", "qty": int}
medicines = {
	"Paracetamol": [
		{"batch_id": "B001", "expiry": "2025-12-01", "qty": 100},
		{"batch_id": "B002", "expiry": "2025-11-25", "qty": 50},
	],
	"Amoxicillin": [
		{"batch_id": "B010", "expiry": "2025-10-15", "qty": 80},
	]
}

# Secondary structures for efficient operations
# min-heap of (expiry_date, medicine_name, batch_id)
_expiry_min_heap = []
# sorted list of (expiry_date, medicine_name, batch_id)
_expiry_sorted = []


def parse_date(date_str: str) -> datetime.date:
	return datetime.strptime(date_str, "%Y-%m-%d").date()


def rebuild_indexes() -> None:
	"""Rebuild heap and sorted list from medicines dict for simplicity and consistency."""
	global _expiry_min_heap, _expiry_sorted
	_expiry_min_heap = []
	_expiry_sorted = []
	for med_name, batches in medicines.items():
		for b in batches:
			try:
				exp = parse_date(b["expiry"])
			except Exception:
				# Skip bad entries silently
				continue
			item = (exp, med_name, b["batch_id"])
			_expiry_min_heap.append(item)
			_expiry_sorted.append(item)
	heapq.heapify(_expiry_min_heap)
	_expiry_sorted.sort(key=lambda x: x[0])


def add_or_update_batch(medicine_name: str, batch_id: str, expiry: str, qty: int) -> None:
	"""Add a new batch or update existing batch for a medicine."""
	if not medicine_name or not batch_id:
		return
	medicine_name = medicine_name.strip()
	batch_id = batch_id.strip()
	if medicine_name not in medicines:
		medicines[medicine_name] = []
	# Check if batch exists
	existing = None
	for b in medicines[medicine_name]:
		if b["batch_id"] == batch_id:
			existing = b
			break
	if existing:
		existing["expiry"] = expiry
		existing["qty"] = qty
	else:
		medicines[medicine_name].append({
			"batch_id": batch_id,
			"expiry": expiry,
			"qty": qty
		})
	rebuild_indexes()


def delete_batch(medicine_name: str, batch_id: str) -> bool:
	"""Delete a batch. Returns True if deleted."""
	if medicine_name not in medicines:
		return False
	new_list = [b for b in medicines[medicine_name] if b["batch_id"] != batch_id]
	deleted = len(new_list) != len(medicines[medicine_name])
	medicines[medicine_name] = new_list
	# Clean up empty medicine
	if not medicines[medicine_name]:
		del medicines[medicine_name]
	if deleted:
		rebuild_indexes()
	return deleted


def get_expiring_within(days: int):
	"""Return list of (date, med, batch) expiring within N days using binary search on sorted list."""
	if days < 0:
		return []
	today = datetime.today().date()
	cutoff = today + timedelta(days=days)
	# Find range in _expiry_sorted where date in [today, cutoff]
	# Extract only the date for bisect keys
	dates_only = [t[0] for t in _expiry_sorted]
	left = bisect_left(dates_only, today)
	right = bisect_right(dates_only, cutoff)
	return _expiry_sorted[left:right]


def days_until(expiry_str: str) -> int:
	try:
		exp = parse_date(expiry_str)
		return (exp - datetime.today().date()).days
	except Exception:
		return 0


# Initialize indexes on startup
rebuild_indexes()


# ------------------------------
# Routes
# ------------------------------
@app.route("/")
def index():
	return render_template("index.html")


@app.route("/uploader", methods=["GET", "POST"])
def uploader():
	if request.method == "POST":
		action = request.form.get("action")  # add_update | delete
		medicine_name = request.form.get("medicine_name", "").strip()
		batch_id = request.form.get("batch_id", "").strip()
		expiry = request.form.get("expiry", "").strip()
		qty_raw = request.form.get("qty", "").strip()

		if action == "delete":
			if not medicine_name or not batch_id:
				flash("Provide Medicine Name and Batch ID to delete.", "error")
			else:
				if delete_batch(medicine_name, batch_id):
					flash(f"Deleted batch {batch_id} of {medicine_name}.", "success")
				else:
					flash("Batch not found.", "error")
			return redirect(url_for("uploader"))

		# add or update
		if not medicine_name or not batch_id or not expiry or not qty_raw:
			flash("All fields are required for Add/Update.", "error")
			return redirect(url_for("uploader"))
		try:
			_ = parse_date(expiry)
		except Exception:
			flash("Invalid expiry date format. Use YYYY-MM-DD.", "error")
			return redirect(url_for("uploader"))
		try:
			qty = int(qty_raw)
			if qty < 0:
				raise ValueError()
		except Exception:
			flash("Quantity must be a non-negative integer.", "error")
			return redirect(url_for("uploader"))

		add_or_update_batch(medicine_name, batch_id, expiry, qty)
		flash("Batch added/updated successfully.", "success")
		return redirect(url_for("uploader"))

	# GET
	# Sort view by medicine then by expiry
	rows = []
	today = datetime.today().date()
	for med, batches in medicines.items():
		for b in batches:
			exp = parse_date(b["expiry"])
			dleft = (exp - today).days
			level = "ok"
			if dleft <= 7:
				level = "danger"
			elif dleft <= 30:
				level = "warning"
			rows.append({
				"medicine": med,
				"batch_id": b["batch_id"],
				"expiry": b["expiry"],
				"qty": b["qty"],
				"days_left": dleft,
				"level": level,
			})
	rows.sort(key=lambda r: (r["medicine"].lower(), parse_date(r["expiry"])))
	return render_template("uploader.html", medicines_view=rows, today=today)


@app.route("/viewer")
def viewer():
	days_param = request.args.get("days", "30")
	try:
		days = int(days_param)
		if days < 0:
			days = 30
	except Exception:
		days = 30
	expiring = get_expiring_within(days)

	# Flatten all batches for table; sort by expiry ascending and annotate levels
	all_rows = []
	today = datetime.today().date()
	for med, batches in medicines.items():
		for b in batches:
			exp = parse_date(b["expiry"])
			dleft = (exp - today).days
			level = "ok"
			if dleft <= 7:
				level = "danger"
			elif dleft <= 30:
				level = "warning"
			all_rows.append({
				"medicine": med,
				"batch_id": b["batch_id"],
				"expiry": b["expiry"],
				"qty": b["qty"],
				"days_left": dleft,
				"level": level,
			})
	all_rows.sort(key=lambda r: parse_date(r["expiry"]))

	# Map expiring tuples to enriched rows
	expiring_rows = []
	for exp_date, med, batch in expiring:
		# find matching batch to show qty
		qty = None
		for b in medicines.get(med, []):
			if b["batch_id"] == batch:
				qty = b["qty"]
				break
		dleft = (exp_date - today).days
		level = "ok"
		if dleft <= 7:
			level = "danger"
		elif dleft <= 30:
			level = "warning"
		expiring_rows.append({
			"medicine": med,
			"batch_id": batch,
			"expiry": exp_date.strftime("%Y-%m-%d"),
			"qty": qty if qty is not None else 0,
			"days_left": dleft,
			"level": level,
		})

	return render_template(
		"viewer.html",
		all_rows=all_rows,
		expiring=expiring_rows,
		days=days,
		today=today
	)


if __name__ == "__main__":
	app.run(debug=True)


