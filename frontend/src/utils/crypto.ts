import CryptoJS from 'crypto-js'

/**
 * 使用 crypto-js SHA256 加密密码
 * @param password 原始密码
 * @returns Promise<string> 加密后的密码哈希
 */
export async function encryptPassword(password: string): Promise<string> {
  try {
    // 使用 SHA256 哈希算法加密密码
    const hash = CryptoJS.SHA256(password).toString()
    return hash
  } catch (error) {
    console.error('密码加密失败:', error)
    throw new Error('密码加密失败')
  }
}

/**
 * 同步版本的密码加密（用于兼容性）
 * @param password 原始密码
 * @returns string 加密后的密码哈希
 */
export function encryptPasswordSync(password: string): string {
  try {
    // 使用 SHA256 哈希算法加密密码
    const hash = CryptoJS.SHA256(password).toString()
    return hash
  } catch (error) {
    console.error('密码加密失败:', error)
    throw new Error('密码加密失败')
  }
}

/**
 * 使用 AES 加密密码（如果需要可逆加密）
 * @param password 原始密码
 * @param secretKey 密钥（可选，默认使用固定密钥）
 * @returns string 加密后的密码
 */
export function encryptPasswordAES(password: string, secretKey?: string): string {
  try {
    const key = secretKey || 'fcsa-ai-secret-key-2025'
    const encrypted = CryptoJS.AES.encrypt(password, key).toString()
    return encrypted
  } catch (error) {
    console.error('密码加密失败:', error)
    throw new Error('密码加密失败')
  }
}

/**
 * 使用 AES 解密密码（如果需要可逆加密）
 * @param encryptedPassword 加密后的密码
 * @param secretKey 密钥（可选，默认使用固定密钥）
 * @returns string 解密后的密码
 */
export function decryptPasswordAES(encryptedPassword: string, secretKey?: string): string {
  try {
    const key = secretKey || 'fcsa-ai-secret-key-2025'
    const decrypted = CryptoJS.AES.decrypt(encryptedPassword, key)
    return decrypted.toString(CryptoJS.enc.Utf8)
  } catch (error) {
    console.error('密码解密失败:', error)
    throw new Error('密码解密失败')
  }
}
