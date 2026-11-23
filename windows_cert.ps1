$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::InputEncoding = [Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$request = [Console]::In.ReadToEnd() | ConvertFrom-Json

function Read-Certificates($name, $location) {
    $store = [Security.Cryptography.X509Certificates.X509Store]::new($name, $location)
    try {
        $store.Open([Security.Cryptography.X509Certificates.OpenFlags]::ReadOnly)
        $store.Certificates
    } finally {
        $store.Dispose()
    }
}

if ($request.operation -eq 'list') {
    $now = Get-Date
    $seen = @{}
    $certificates = @(
        foreach ($location in @('CurrentUser', 'LocalMachine')) {
            Read-Certificates 'My' $location | Where-Object {
                $_.HasPrivateKey -and $_.PublicKey.Oid.Value -in @('1.2.840.113549.1.1.1', '1.2.840.10045.2.1') -and $_.NotBefore -le $now -and $_.NotAfter -ge $now
            } | ForEach-Object {
                $usage = $_.Extensions | Where-Object { $_.Oid.Value -eq '2.5.29.15' } | Select-Object -First 1
                if ((!$usage -or ($usage.KeyUsages -band 192)) -and !$seen.ContainsKey($_.Thumbprint)) {
                    $seen[$_.Thumbprint] = $true
                    @{
                        thumbprint = $_.Thumbprint
                        location = $location
                        name = $_.GetNameInfo([Security.Cryptography.X509Certificates.X509NameType]::SimpleName, $false)
                        issuer = $_.GetNameInfo([Security.Cryptography.X509Certificates.X509NameType]::SimpleName, $true)
                        expiry = $_.NotAfter.ToString('yyyy-MM-dd')
                        der = [Convert]::ToBase64String($_.RawData)
                    }
                }
            }
        }
    )
    ConvertTo-Json -InputObject $certificates -Compress
    exit
}

if ($request.thumbprint -notmatch '^[a-fA-F0-9]{40}$') { throw 'Identificador de certificado no válido.' }
if ($request.location -notin @('CurrentUser', 'LocalMachine')) { throw 'Almacén de certificados no válido.' }
$certificate = Read-Certificates 'My' $request.location | Where-Object Thumbprint -eq $request.thumbprint | Select-Object -First 1
if (!$certificate) { throw 'El certificado ya no está disponible en el almacén de Windows.' }

if ($request.operation -eq 'chain') {
    $chain = @()
    $current = $certificate
    $authorities = @(Read-Certificates 'CA' 'CurrentUser') + @(Read-Certificates 'CA' 'LocalMachine')
    for ($step = 0; $step -lt 8 -and $current.Issuer -ne $current.Subject; $step++) {
        $issuer = $authorities | Where-Object {
            $_.Subject -eq $current.Issuer -and $_.Thumbprint -ne $current.Thumbprint
        } | Select-Object -First 1
        if (!$issuer -or $issuer.Subject -eq $issuer.Issuer) { break }
        $chain += [Convert]::ToBase64String($issuer.RawData)
        $current = $issuer
    }
    ConvertTo-Json -InputObject $chain -Compress
    exit
}

if ($request.operation -ne 'sign') { throw 'Operación de certificado desconocida.' }
$data = [Convert]::FromBase64String($request.data)
$hash = [Security.Cryptography.HashAlgorithmName]::SHA256
if ($certificate.PublicKey.Oid.Value -eq '1.2.840.10045.2.1') {
    $key = [Security.Cryptography.X509Certificates.ECDsaCertificateExtensions]::GetECDsaPrivateKey($certificate)
    if (!$key) { throw 'No se pudo abrir la clave privada ECDSA desde Windows.' }
    try {
        $signature = $key.SignData($data, $hash)
        ConvertTo-Json -InputObject ([Convert]::ToBase64String($signature)) -Compress
    } finally {
        $key.Dispose()
    }
    exit
}
$key = [Security.Cryptography.X509Certificates.RSACertificateExtensions]::GetRSAPrivateKey($certificate)
if (!$key) { throw 'No se pudo abrir la clave privada RSA desde Windows.' }
try {
    $padding = [Security.Cryptography.RSASignaturePadding]::Pkcs1
    $signature = $key.SignData($data, $hash, $padding)
    ConvertTo-Json -InputObject ([Convert]::ToBase64String($signature)) -Compress
} finally {
    $key.Dispose()
}
