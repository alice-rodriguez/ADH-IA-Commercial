function App() {
  return (
    <div className="flex flex-col min-h-screen bg-white">
      <header className="bg-adh-black flex items-center gap-4 px-6 py-4">
        <img src="/picto-adh.png" alt="Pictogramme ADH" className="h-10" />
        <img src="/logo-adh.png" alt="Logo ADH" className="h-8" />
      </header>

      <main className="flex-1 flex flex-col items-center justify-center gap-4 px-6">
        <h1 className="text-4xl font-semibold text-adh-black tracking-tight">
          Veille commerciale IT
        </h1>
        <p className="text-xl text-adh-orange font-medium">
          Interface en construction
        </p>
        <p className="text-sm text-gray-400 mt-8">
          Backend API : http://localhost:8000
        </p>
      </main>
    </div>
  )
}

export default App
