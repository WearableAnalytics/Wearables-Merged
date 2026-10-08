const _months = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
];

String formatDate(DateTime d) => '${d.day} ${_months[d.month - 1]} ${d.year}';

String formatTime(DateTime d) =>
    '${d.hour.toString().padLeft(2, '0')}:${d.minute.toString().padLeft(2, '0')}';

String formatDateTime(DateTime d) => '${formatDate(d)}, ${formatTime(d)}';

/// "Today, 14:05", "Yesterday, 09:12" or a full date.
String formatRelative(DateTime d, {DateTime? now}) {
  final reference = now ?? DateTime.now();
  final today = DateTime(reference.year, reference.month, reference.day);
  final day = DateTime(d.year, d.month, d.day);
  final diff = today.difference(day).inDays;
  if (diff == 0) return 'Today, ${formatTime(d)}';
  if (diff == 1) return 'Yesterday, ${formatTime(d)}';
  return formatDate(d);
}
