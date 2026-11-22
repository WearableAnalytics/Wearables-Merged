import 'package:flutter/material.dart';
import '../services/polar_setup.dart';

class PolarSetupPage extends StatefulWidget {
  const PolarSetupPage({super.key, required this.band});
  final String band;
  @override
  State<PolarSetupPage> createState() => _PolarSetupPageState();
}

class _PolarSetupPageState extends State<PolarSetupPage> {
  final form = GlobalKey<FormState>();
  final values = <String, num>{};
  DateTime? birthday;
  int? sex, training, typicalDay;
  String? error;

  Widget number(
    String label,
    String key,
    int min,
    int max, {
    bool decimal = false,
  }) {
    num? parse(String? text) {
      final value = (text ?? '').trim().replaceAll(',', '.');
      return decimal ? double.tryParse(value) : int.tryParse(value);
    }

    return TextFormField(
      decoration: InputDecoration(labelText: label, hintText: '$min–$max'),
      keyboardType: TextInputType.numberWithOptions(decimal: decimal),
      validator: (text) {
        final n = parse(text);
        return n == null || !n.isFinite || n < min || n > max
            ? 'Enter a value from $min to $max.'
            : null;
      },
      onSaved: (text) => values[key] = parse(text)!,
    );
  }

  Widget choice(
    String label,
    Map<int, String> options,
    ValueChanged<int?> change,
  ) => DropdownButtonFormField<int>(
    decoration: InputDecoration(labelText: label),
    items: options.entries
        .map((e) => DropdownMenuItem(value: e.key, child: Text(e.value)))
        .toList(),
    onChanged: change,
    validator: (value) => value == null ? 'Choose an option.' : null,
  );

  Future<void> pickDate() async {
    final today = DateTime.now();
    final yesterday = DateTime(today.year, today.month, today.day - 1);
    final date = await showDatePicker(
      context: context,
      firstDate: DateTime(1900),
      lastDate: yesterday,
      initialDate: birthday ?? DateTime(today.year - 30, 1, 1),
      initialDatePickerMode: DatePickerMode.year,
    );
    if (mounted && date != null) setState(() => birthday = date);
  }

  void submit() {
    final valid = form.currentState!.validate();
    if (birthday == null || !valid) {
      setState(
        () => error = birthday == null ? 'Select your date of birth.' : null,
      );
      return;
    }
    form.currentState!.save();
    int integer(String key) => values[key]!.toInt();
    if (integer('resting') >= integer('maximum')) {
      setState(
        () => error = 'Resting heart rate must be below maximum heart rate.',
      );
      return;
    }
    Navigator.pop(
      context,
      PolarSetupProfile(
        birthday: birthday!,
        sex: sex!,
        height: values['height']!.toDouble(),
        weight: values['weight']!.toDouble(),
        maximum: integer('maximum'),
        resting: integer('resting'),
        vo2: integer('vo2'),
        training: training!,
        typicalDay: typicalDay!,
        sleepMinutes: integer('sleep'),
      ),
    );
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Set up Polar 360')),
    body: SafeArea(
      child: Form(
        key: form,
        child: ListView(
          padding: const EdgeInsets.all(20),
          children: [
            Text(widget.band, style: Theme.of(context).textTheme.titleMedium),
            const Text(
              'Keep the band on its charger near this phone. Accept the Bluetooth pairing prompt if shown. Polar uses these settings on the band to calculate activity and sleep. This step sends the settings only to your band. You can choose study sharing separately.',
            ),
            OutlinedButton(
              onPressed: pickDate,
              child: Text(
                birthday == null
                    ? 'Select date of birth'
                    : MaterialLocalizations.of(
                        context,
                      ).formatMediumDate(birthday!),
              ),
            ),
            choice('Biological sex used by Polar', {
              1: 'Male',
              2: 'Female',
            }, (v) => sex = v),
            number('Height (cm)', 'height', 90, 240, decimal: true),
            number('Weight (kg)', 'weight', 15, 300, decimal: true),
            number('Maximum heart rate (bpm)', 'maximum', 100, 240),
            number('Resting heart rate (bpm)', 'resting', 20, 120),
            number('VO₂ max (ml/kg/min)', 'vo2', 10, 95),
            choice('Training background', {
              10: 'Occasional',
              20: 'Regular',
              30: 'Frequent',
              40: 'Heavy',
              50: 'Semi-professional',
              60: 'Professional',
            }, (v) => training = v),
            choice('Typical day', {
              1: 'Mostly sitting',
              2: 'Mostly standing',
              3: 'Mostly moving',
            }, (v) => typicalDay = v),
            number('Nightly sleep goal (minutes)', 'sleep', 300, 660),
            if (error != null)
              Text(
                error!,
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            FilledButton(
              onPressed: submit,
              child: const Text('Save settings to this band'),
            ),
          ],
        ),
      ),
    ),
  );
}
