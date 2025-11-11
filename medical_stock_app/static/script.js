function onDaysChange() {
	const form = document.getElementById('daysForm');
	if (form) form.submit();
}

function onUploaderSubmit(e) {
	const form = e.target;
	const action = form.querySelector('input[name="action"]:checked')?.value;
	if (action === 'delete') {
		const med = form.medicine_name.value || '';
		const batch = form.batch_id.value || '';
		if (!confirm(`Delete batch "${batch}" of "${med}"? This cannot be undone.`)) {
			e.preventDefault();
			return false;
		}
		// For delete, we don't require expiry/qty
		form.expiry.removeAttribute('required');
		form.qty.removeAttribute('required');
	}
	return true;
}

// Client-side filter for All Stock table on viewer
document.addEventListener('DOMContentLoaded', () => {
	const search = document.getElementById('searchAll');
	const tbody = document.getElementById('allStockBody');
	if (!search || !tbody) return;
	const rows = Array.from(tbody.querySelectorAll('tr'));
	search.addEventListener('input', () => {
		const q = search.value.trim().toLowerCase();
		rows.forEach(row => {
			const cells = row.querySelectorAll('td');
			const med = (cells[0]?.textContent || '').toLowerCase();
			const batch = (cells[1]?.textContent || '').toLowerCase();
			if (!q || med.includes(q) || batch.includes(q)) {
				row.style.display = '';
			} else {
				row.style.display = 'none';
			}
		});
	});
});


