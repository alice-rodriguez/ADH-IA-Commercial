import { useEffect, useState } from 'react'
import { fetchUsers, creerUser, supprimerUser, resetPassword } from '../api'
import type { User } from '../api'
import { useAuth } from '../auth/AuthContext'

type ModalType = 'ajouter' | 'reset' | 'supprimer' | null

export default function PageUsers() {
  const { user: currentUser } = useAuth()
  const [users, setUsers] = useState<User[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [modal, setModal] = useState<ModalType>(null)
  const [selectedUser, setSelectedUser] = useState<User | null>(null)
  const [modalError, setModalError] = useState<string | null>(null)
  const [modalLoading, setModalLoading] = useState(false)

  // Ajouter
  const [newUsername, setNewUsername] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [newPasswordConfirm, setNewPasswordConfirm] = useState('')

  // Reset
  const [resetPwd, setResetPwd] = useState('')
  const [resetPwdConfirm, setResetPwdConfirm] = useState('')

  useEffect(() => {
    chargerUsers()
  }, [])

  async function chargerUsers() {
    setLoading(true)
    try {
      setUsers(await fetchUsers())
    } catch {
      setError('Impossible de charger les utilisateurs.')
    } finally {
      setLoading(false)
    }
  }

  function ouvrirModal(type: ModalType, u?: User) {
    setModal(type)
    setSelectedUser(u ?? null)
    setModalError(null)
    setNewUsername('')
    setNewPassword('')
    setNewPasswordConfirm('')
    setResetPwd('')
    setResetPwdConfirm('')
  }

  function fermerModal() {
    setModal(null)
    setSelectedUser(null)
    setModalError(null)
  }

  async function handleAjouter(e: React.FormEvent) {
    e.preventDefault()
    if (newPassword !== newPasswordConfirm) {
      setModalError('Les mots de passe ne correspondent pas.')
      return
    }
    setModalLoading(true)
    setModalError(null)
    try {
      await creerUser(newUsername, newPassword)
      await chargerUsers()
      fermerModal()
    } catch (err) {
      setModalError(err instanceof Error ? err.message : 'Erreur')
    } finally {
      setModalLoading(false)
    }
  }

  async function handleReset(e: React.FormEvent) {
    e.preventDefault()
    if (resetPwd !== resetPwdConfirm) {
      setModalError('Les mots de passe ne correspondent pas.')
      return
    }
    setModalLoading(true)
    setModalError(null)
    try {
      await resetPassword(selectedUser!.id, resetPwd)
      fermerModal()
    } catch (err) {
      setModalError(err instanceof Error ? err.message : 'Erreur')
    } finally {
      setModalLoading(false)
    }
  }

  async function handleSupprimer() {
    setModalLoading(true)
    setModalError(null)
    try {
      await supprimerUser(selectedUser!.id)
      await chargerUsers()
      fermerModal()
    } catch (err) {
      setModalError(err instanceof Error ? err.message : 'Erreur')
    } finally {
      setModalLoading(false)
    }
  }

  return (
    <main className="flex-1 p-6 max-w-3xl mx-auto w-full">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-bold text-gray-900">Utilisateurs</h2>
        <button
          onClick={() => ouvrirModal('ajouter')}
          className="bg-adh-orange text-white text-sm font-semibold px-4 py-2 rounded-lg hover:opacity-90 transition-opacity"
        >
          + Ajouter un utilisateur
        </button>
      </div>

      {loading && <p className="text-gray-500 text-sm">Chargement…</p>}
      {error && <p className="text-red-600 text-sm">{error}</p>}

      {!loading && !error && (
        <div className="bg-white rounded-xl shadow overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-3 font-semibold text-gray-600">Nom d'utilisateur</th>
                <th className="text-left px-4 py-3 font-semibold text-gray-600">Date de création</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {users.map(u => {
                const isSelf = currentUser?.user_id === u.id
                return (
                  <tr key={u.id} className="border-b border-gray-100 last:border-0">
                    <td className="px-4 py-3 font-medium text-gray-900">
                      {u.username}
                      {isSelf && (
                        <span className="ml-2 text-xs text-adh-orange font-normal">(vous)</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-gray-500">
                      {new Date(u.date_creation).toLocaleDateString('fr-FR')}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={() => ouvrirModal('reset', u)}
                          className="text-xs text-adh-violet border border-adh-violet rounded px-2 py-1 hover:bg-adh-violet hover:text-white transition-colors"
                        >
                          Réinitialiser le mot de passe
                        </button>
                        <button
                          onClick={() => !isSelf && ouvrirModal('supprimer', u)}
                          disabled={isSelf}
                          title={isSelf ? 'Vous ne pouvez pas vous supprimer vous-même' : undefined}
                          className="text-xs text-red-600 border border-red-300 rounded px-2 py-1 hover:bg-red-600 hover:text-white transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                        >
                          Supprimer
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* ── Modales ── */}
      {modal && (
        <div
          className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4"
          onClick={e => e.target === e.currentTarget && fermerModal()}
        >
          <div className="bg-white rounded-2xl shadow-xl p-6 w-full max-w-sm">

            {/* Ajouter */}
            {modal === 'ajouter' && (
              <form onSubmit={handleAjouter} className="flex flex-col gap-4">
                <h3 className="text-lg font-bold text-gray-900">Ajouter un utilisateur</h3>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Nom d'utilisateur</label>
                  <input
                    type="text"
                    value={newUsername}
                    onChange={e => setNewUsername(e.target.value)}
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-adh-orange"
                    required
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Mot de passe</label>
                  <input
                    type="password"
                    value={newPassword}
                    onChange={e => setNewPassword(e.target.value)}
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-adh-orange"
                    minLength={8}
                    required
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Confirmer le mot de passe</label>
                  <input
                    type="password"
                    value={newPasswordConfirm}
                    onChange={e => setNewPasswordConfirm(e.target.value)}
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-adh-orange"
                    minLength={8}
                    required
                  />
                </div>
                {modalError && <p className="text-red-600 text-sm">{modalError}</p>}
                <div className="flex gap-3 pt-1">
                  <button
                    type="button"
                    onClick={fermerModal}
                    className="flex-1 border border-gray-300 text-gray-700 rounded-lg py-2 text-sm hover:bg-gray-50"
                  >
                    Annuler
                  </button>
                  <button
                    type="submit"
                    disabled={modalLoading}
                    className="flex-1 bg-adh-orange text-white rounded-lg py-2 text-sm font-semibold hover:opacity-90 disabled:opacity-60"
                  >
                    {modalLoading ? 'Création...' : 'Créer'}
                  </button>
                </div>
              </form>
            )}

            {/* Reset mot de passe */}
            {modal === 'reset' && (
              <form onSubmit={handleReset} className="flex flex-col gap-4">
                <h3 className="text-lg font-bold text-gray-900">
                  Réinitialiser le mot de passe
                </h3>
                <p className="text-sm text-gray-600">
                  Utilisateur : <strong>{selectedUser?.username}</strong>
                </p>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Nouveau mot de passe</label>
                  <input
                    type="password"
                    value={resetPwd}
                    onChange={e => setResetPwd(e.target.value)}
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-adh-orange"
                    minLength={8}
                    required
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Confirmer le mot de passe</label>
                  <input
                    type="password"
                    value={resetPwdConfirm}
                    onChange={e => setResetPwdConfirm(e.target.value)}
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-adh-orange"
                    minLength={8}
                    required
                  />
                </div>
                {modalError && <p className="text-red-600 text-sm">{modalError}</p>}
                <div className="flex gap-3 pt-1">
                  <button
                    type="button"
                    onClick={fermerModal}
                    className="flex-1 border border-gray-300 text-gray-700 rounded-lg py-2 text-sm hover:bg-gray-50"
                  >
                    Annuler
                  </button>
                  <button
                    type="submit"
                    disabled={modalLoading}
                    className="flex-1 bg-adh-orange text-white rounded-lg py-2 text-sm font-semibold hover:opacity-90 disabled:opacity-60"
                  >
                    {modalLoading ? 'Enregistrement...' : 'Enregistrer'}
                  </button>
                </div>
              </form>
            )}

            {/* Supprimer */}
            {modal === 'supprimer' && (
              <div className="flex flex-col gap-4">
                <h3 className="text-lg font-bold text-gray-900">Supprimer l'utilisateur</h3>
                <p className="text-sm text-gray-600">
                  Supprimer définitivement <strong>{selectedUser?.username}</strong> ? Cette action est irréversible.
                </p>
                {modalError && <p className="text-red-600 text-sm">{modalError}</p>}
                <div className="flex gap-3 pt-1">
                  <button
                    type="button"
                    onClick={fermerModal}
                    className="flex-1 border border-gray-300 text-gray-700 rounded-lg py-2 text-sm hover:bg-gray-50"
                  >
                    Annuler
                  </button>
                  <button
                    type="button"
                    onClick={handleSupprimer}
                    disabled={modalLoading}
                    className="flex-1 bg-red-600 text-white rounded-lg py-2 text-sm font-semibold hover:bg-red-700 disabled:opacity-60"
                  >
                    {modalLoading ? 'Suppression...' : 'Supprimer'}
                  </button>
                </div>
              </div>
            )}

          </div>
        </div>
      )}
    </main>
  )
}
