import 'package:flutter/material.dart';

import '../data_view_page.dart';
import '../state/app_state.dart';
import 'home_page.dart';
import 'study_page.dart';

/// Root screen. Shows only the welcome flow until a study code is linked,
/// then a tab bar with Home, My data and Study.
class MainPage extends StatefulWidget {
  const MainPage({super.key, this.state});

  /// Injectable for tests; created on demand otherwise.
  final AppState? state;

  @override
  State<MainPage> createState() => _MainPageState();
}

class _MainPageState extends State<MainPage> {
  late final AppState _state = widget.state ?? AppState();
  int _tab = 0;

  @override
  void initState() {
    super.initState();
    if (!_state.loaded) _state.load();
  }

  @override
  void dispose() {
    if (widget.state == null) _state.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: _state,
      builder: (context, _) {
        if (_state.loaded && !_state.isLinked) {
          return HomePage(state: _state);
        }
        return Scaffold(
          body: IndexedStack(
            index: _tab,
            children: [
              HomePage(state: _state),
              const DataViewPage(),
              StudyPage(state: _state),
            ],
          ),
          bottomNavigationBar: DecoratedBox(
            decoration: BoxDecoration(
              border: Border(
                top: BorderSide(color: Theme.of(context).dividerColor),
              ),
            ),
            child: NavigationBar(
              selectedIndex: _tab,
              onDestinationSelected: (i) => setState(() => _tab = i),
              destinations: const [
                NavigationDestination(
                  icon: Icon(Icons.home_outlined),
                  selectedIcon: Icon(Icons.home_rounded),
                  label: 'Home',
                ),
                NavigationDestination(
                  icon: Icon(Icons.insights_outlined),
                  selectedIcon: Icon(Icons.insights_rounded),
                  label: 'My data',
                ),
                NavigationDestination(
                  icon: Icon(Icons.badge_outlined),
                  selectedIcon: Icon(Icons.badge_rounded),
                  label: 'Study',
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}
