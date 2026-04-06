<img width="100%" src="docs/images/logo.svg">

High-Performance Chip Design in Python.

A modern framework for seamless KLayout integration, hierarchical cell caching, and intuitive layout synthesis.

## 🚀 Key Features

- **Smart Layer API**: Pythonic boolean operations (`+`, `-`, `&`, `|`, `^`), sizing, and advanced interaction filters (`interacting`, `inside`, `outside`, `overlapping`).
- **Hierarchical Caching**: Seamless memory and disk caching with **Transitive Source Hashing** that detects changes in your code, its dependencies, and external library versions.
- **Parallel Generation**: Leverage multi-core CPUs with asynchronous cell generation for massive design speedups.
- **Hierarchical Netlist Extraction**: Recover netlists from physical layouts via spatial collision detection and recursive property extraction.
- **Connectivity & Routing**: Snap-based hierarchical connectivity and automated component chaining for error-free assembly.
- **Performance Insights**: Detailed design statistics tracking cache hits, build times, and call counts for optimization.
- **Jupyter & KLayout Native**: Interactive GDSII rendering in notebooks and live synchronization with KLayout via KLive.

## 📦 Installation

```bash
pip install gdswell
```

## 📖 Documentation

For more information and examples, visit the [Documentation Site](https://HelgeGehring.github.io/gdswell/).
